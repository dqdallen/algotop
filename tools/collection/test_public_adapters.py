import json
import tempfile
import unittest
from pathlib import Path
import collect

class PublicAdaptersTests(unittest.TestCase):
 def test_sitemap_urlset_metadata_no_fetch_recursion(self):
  self.assertIn('sitemap',collect.ADAPTERS)
  body=b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://www.nowcoder.com/discuss/123</loc><lastmod>2026-10-26</lastmod></url><url><loc>https://www.nowcoder.com/sitemap1.xml</loc></url></urlset>'
  rows=collect.discover('sitemap',body,'https://www.nowcoder.com/sitemap.xml',10)
  self.assertEqual(rows,[('https://www.nowcoder.com/discuss/123','',None,{'sitemap_entry_kind':'url','last_modified_claim':'2026-10-26'}),('https://www.nowcoder.com/sitemap1.xml','',None,{'sitemap_entry_kind':'url','last_modified_claim':None})])
 def test_sitemap_index_bounded(self):
  self.assertIn('sitemap',collect.ADAPTERS)
  body=b'<sitemapindex><sitemap><loc>https://example.org/a.xml</loc></sitemap><sitemap><loc>https://example.org/b.xml</loc></sitemap></sitemapindex>'
  self.assertEqual(len(collect.discover('sitemap',body,'https://example.org/sitemap.xml',1)),1)
 def test_sitemap_rejects_entities(self):
  self.assertIn('sitemap',collect.ADAPTERS)
  with self.assertRaises(ValueError):collect.discover('sitemap',b'<!DOCTYPE a><urlset/>','https://example.org/sitemap.xml',10)
 def test_index_kind_does_not_require_xml_extension(self):
  rows=collect.discover('sitemap',b'<sitemapindex><sitemap><loc>https://example.org/index</loc></sitemap></sitemapindex>','https://example.org/sitemap.xml',10)
  self.assertEqual(len(rows[0]),4)
  self.assertEqual(rows[0][3]['sitemap_entry_kind'],'sitemap')
 def test_github_contents_only_public_links_not_content(self):
  self.assertIn('github_contents',collect.ADAPTERS)
  body=json.dumps([{'type':'file','name':'Interview.md','html_url':'https://github.com/Owner/Repo/blob/main/Interview.md','content':'never copy me'},{'type':'dir','name':'notes','html_url':'https://github.com/Owner/Repo/tree/main/notes'}]).encode()
  rows=collect.discover('github_contents',body,'https://api.github.com/repos/Owner/Repo/contents',10)
  self.assertEqual(len(rows),2);self.assertEqual(rows[0][1],'Interview.md');self.assertNotIn('never copy me',str(rows))
 def test_github_kind_uses_api_type_not_path_substring(self):
  body=json.dumps([{'type':'file','name':'x.md','html_url':'https://github.com/Owner/Repo/blob/main/tree/x.md'}]).encode()
  rows=collect.discover('github_contents',body,'https://api.github.com/repos/Owner/Repo/contents',10)
  self.assertEqual(len(rows[0]),4)
  self.assertEqual(rows[0][3]['github_entry_type'],'file')
 def test_github_wrong_repo_response_rejected(self):
  self.assertIn('github_contents',collect.ADAPTERS)
  body=json.dumps([{'type':'file','name':'x','html_url':'https://github.com/Attacker/Other/blob/main/x'}]).encode()
  self.assertEqual(collect.discover('github_contents',body,'https://api.github.com/repos/Owner/Repo/contents',10),[])
 def test_sitemap_retains_schema_kind_and_last_modified(self):
  self.assertIn('sitemap',collect.ADAPTERS)
  with tempfile.TemporaryDirectory() as d:
   replies=[(404,'text/plain',b''),(200,'text/xml',b'<urlset><url><loc>https://example.org/sitemap1.xml</loc><lastmod>2026-10-26</lastmod></url></urlset>')]
   c=collect.Collector({'example.org':{'terms_status':'permitted','terms_url':'https://example.org/robots.txt','reviewed_at':'2026-10-26','allowed_exact_paths':['/sitemap.xml']}},Path(d)/'c',http=lambda _:replies.pop(0),today='2026-10-26',sleeper=lambda _:None)
   r=c.run([{'id':'s','platform':'Nowcoder','adapter':'sitemap','enabled':True,'url':'https://example.org/sitemap.xml'}],network=True)
   self.assertEqual(r['requests'],2);self.assertEqual(r['candidates'][0].get('candidate_kind'),'sitemap_url');self.assertEqual(r['question_candidates'],[])
   self.assertIsNone(r['candidates'][0]['publication_date_claim']);self.assertEqual(r['candidates'][0].get('last_modified_claim'),'2026-10-26')
if __name__=='__main__':unittest.main()
