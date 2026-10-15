import base64
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import make_report_html as report


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWZkAAAAASUVORK5CYII="
)


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "images").mkdir()
        for name in ["diagram.png", "구조도 (최종).png", "diagram(v1).png"]:
            (self.root / "images" / name).write_bytes(PNG)

    def render(self, md):
        ctx = report.Context(set(), 2, self.root)
        return report.parse_blocks(md.splitlines(), ctx)

    def test_relative_path_does_not_depend_on_working_directory(self):
        with patch.object(Path, "cwd", return_value=Path("/unrelated")):
            result = self.render("![구조도](images/diagram.png)")
        self.assertIn('src="data:image/png;base64,' + base64.b64encode(PNG).decode(), result)
        self.assertNotIn(str(self.root), result)

    def test_spaces_unicode_and_parentheses(self):
        for path in ["<images/구조도 (최종).png>", "images/diagram(v1).png",
                     "images/%EA%B5%AC%EC%A1%B0%EB%8F%84%20%28%EC%B5%9C%EC%A2%85%29.png"]:
            with self.subTest(path=path):
                self.assertIn('<img ', self.render(f'![설명]({path})'))

    def test_caption_notes_and_shared_numbering(self):
        md = '''도표: 솔루션 구조

![설명](images/diagram.png)

자료: 팀 발표자료.

주: 논리적 구성입니다.

도표: 결과

| 항목 | 결과 |
| --- | --- |
| 시험 | 확인 |
'''
        result = self.render(md)
        self.assertIn('도표 1', result)
        self.assertIn('도표 2', result)
        self.assertIn('class="exhibit image-fig"', result)
        self.assertIn('class="ex-note">자료:', result)
        self.assertIn('class="ex-note">주:', result)
        self.assertNotIn('<p>도표:', result)

    def test_alt_and_title_are_escaped(self):
        result = self.render('![<bad> & "quote"](images/diagram.png "구조 설명")')
        self.assertIn('alt="&lt;bad&gt; &amp; &quot;quote&quot;"', result)
        self.assertIn('title="구조 설명"', result)
        self.assertIn('class="ex-title">구조 설명', result)

    def test_image_on_next_line_starts_figure(self):
        result = self.render('앞 문단\n![구조](images/diagram.png)\n뒤 문단')
        self.assertTrue(result.startswith('<p>앞 문단</p>\n<figure'))
        self.assertTrue(result.endswith('<p>뒤 문단</p>'))

    def test_inline_images_and_links(self):
        result = self.render('본문 ![그림](images/diagram.png) [링크](https://example.org) 끝')
        self.assertIn('<p>본문 <img ', result)
        self.assertIn('<a href="https://example.org">링크</a>', result)
        self.assertNotIn('<figure', result)

    def test_code_examples_are_not_loaded(self):
        result = self.render('`![그림](missing.png)`\n\n```md\n![그림](missing.png)\n```')
        self.assertNotIn('<img', result)
        self.assertIn('missing.png', result)

    def test_errors_are_explicit(self):
        for path, error in [('missing.png', '읽을 수 없습니다'),
                            ('https://example.org/a.png', '로컬 파일'),
                            ('images/a.html', '지원하지 않는')]:
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, error):
                self.render(f'![그림]({path})')

    def test_repeated_images_are_read_once(self):
        with patch.object(Path, 'read_bytes', return_value=PNG) as read:
            self.render('![첫 그림](images/diagram.png)\n\n![둘째](images/diagram.png)')
            self.assertEqual(read.call_count, 1)

    def test_svg_is_embedded_as_image_not_active_markup(self):
        (self.root / 'images' / 'drawing.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
        result = self.render('![벡터](images/drawing.svg)')
        self.assertIn('data:image/svg+xml;base64,', result)
        self.assertNotIn('<svg', result)

    def test_cli_embeds_images_from_markdown_directory(self):
        md = self.root / 'report.md'
        md.write_text('# 보고서\n\n## 1. 구조\n\n![그림](images/diagram.png)')
        script = Path(report.__file__).resolve()
        output = self.root / 'out' / 'report.html'
        result = subprocess.run([sys.executable, str(script), str(md), '-o', str(output),
                                 '--cover', str(self.root / 'images' / 'diagram.png')],
                                cwd=self.root.parent, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = output.read_text()
        self.assertIn('class="report-image" src="data:image/png;base64,', text)
        self.assertFalse((output.parent / '_assets').exists())
        self.assertFalse(output.with_suffix('.pdf').exists())
        md.write_text('# 보고서\n\n![그림](missing.png)')
        output.unlink()
        result = subprocess.run([sys.executable, str(script), str(md), '-o', str(output),
                                 '--cover', str(self.root / 'images' / 'diagram.png')],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('이미지를 읽을 수 없습니다', result.stderr)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
