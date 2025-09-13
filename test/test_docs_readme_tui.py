import unittest


class TestReadmeTuiSection(unittest.TestCase):
    def test_readme_mentions_tui_and_extras(self):
        with open('README.md', 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('--tui', content)
        self.assertIn('pip install .[tui]', content)


if __name__ == '__main__':
    unittest.main()

