"""
Unit tests for Raw Directory Index Crawler.
"""

import unittest
from ripper.index_crawler import is_directory_index, parse_directory_index

SAMPLE_APACHE_INDEX = """
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">
<html>
 <head>
  <title>Index of /movies/2026</title>
 </head>
 <body>
<h1>Index of /movies/2026</h1>
<pre><img src="/icons/blank.gif" alt="Icon "> <a href="?C=N;O=D">Name</a>                    <a href="?C=M;O=A">Last modified</a>      <a href="?C=S;O=A">Size</a>  <a href="?C=D;O=A">Description</a><hr><img src="/icons/back.gif" alt="[PARENTDIR]"> <a href="/movies/">Parent Directory</a>                             -   
<img src="/icons/movie.gif" alt="[VID]"> <a href="Spider-Man.2026.1080p.HQ.mkv">Spider-Man.2026.1080p.HQ.mkv</a> 2026-03-01 12:00  3.2G  
<img src="/icons/movie.gif" alt="[VID]"> <a href="Avatar.3.2025.720p.HEVC.mp4">Avatar.3.2025.720p.HEVC.mp4</a>  2026-02-28 10:15  1.1G  
<img src="/icons/text.gif" alt="[TXT]"> <a href="info.txt">info.txt</a>                     2026-03-01 12:01  1.2K  
<hr></pre>
</body></html>
"""


class TestIndexCrawler(unittest.TestCase):
    def test_is_directory_index(self):
        self.assertTrue(is_directory_index(SAMPLE_APACHE_INDEX))
        self.assertFalse(is_directory_index("<html><body><h1>Hello World</h1></body></html>"))

    def test_parse_directory_index(self):
        results = parse_directory_index(SAMPLE_APACHE_INDEX, "https://storage.cdn-direct.org/movies/2026/")
        self.assertEqual(len(results), 2)
        fname1, url1 = results[0]
        fname2, url2 = results[1]

        self.assertEqual(fname1, "Spider-Man.2026.1080p.HQ.mkv")
        self.assertEqual(url1, "https://storage.cdn-direct.org/movies/2026/Spider-Man.2026.1080p.HQ.mkv")
        self.assertEqual(fname2, "Avatar.3.2025.720p.HEVC.mp4")
        self.assertEqual(url2, "https://storage.cdn-direct.org/movies/2026/Avatar.3.2025.720p.HEVC.mp4")
