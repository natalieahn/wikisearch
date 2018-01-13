# Class and methods for looking up words in Wikipedia API and relating to WordNet synsets
#
# Natalie Ahn
# 1/13/2017
#
# Class: WikiSearch
# Public methods:
#     get_wiki_synset(terms):   Takes a term to search for, and returns the name of a
#                               matching WordNet synset as used in the NLTK interface
#                               (e.g. 'person.n.01').

import re, xlrd, xlwt
import urllib.parse
from urllib.request import urlopen
from lxml import html
import json
from nltk.corpus import wordnet as wn
from time import sleep
from nltk.metrics.distance import edit_distance
from nltk.stem.wordnet import WordNetLemmatizer


class WikiSearch:
	categ_synsets = {}
	regexps = {}
	pronouns = {}
	url_base = 'https://en.wikipedia.org/w/api.php?format=json&action=query'
	sleep_time_btw_queries = 2

	def __init__(self, data_dir=''):
		self.lemmatizer = WordNetLemmatizer()
		self._load_categ_synsets(data_dir)
		self._load_regexps(data_dir)
		self._load_pronouns(data_dir)

	def _load_categ_synsets(self, data_dir):
		with xlrd.open_workbook(data_dir+'/rule_files/wiki_rules.xlsx') as wb:
			sheet = wb.sheet_by_name('categ_synsets')
			for r in range(sheet.nrows):
				row = sheet.row_values(r)
				for term in row[1].split('|'):
					self.categ_synsets[term] = row[0]

	def _load_regexps(self, data_dir):
		with xlrd.open_workbook(data_dir+'/rule_files/wiki_rules.xlsx') as wb:
			sheet = wb.sheet_by_name('regexps')
			for r in range(sheet.nrows):
				row = sheet.row_values(r)
				self.regexps[row[0]] = row[1]

	def _load_pronouns(self, data_dir):
		with xlrd.open_workbook(data_dir+'/rule_files/wiki_rules.xlsx') as wb:
			sheet = wb.sheet_by_name('pronouns')
			for r in range(sheet.nrows):
				row = sheet.row_values(r)
				self.pronouns[row[1]] = row[0]

	def get_wiki_synset(self, term):
		url_title = urllib.parse.quote(term)
		url = self.url_base + '&titles=%s&prop=categories|pageterms|extracts' % url_title
		response = self._get_wiki_response(url)
		rterms = self._get_response_terms(response)
		synset = self._get_first_synset(rterms)
		if synset: return synset
		else: return self._get_wiki_search_synset(term)

	def _get_wiki_response(self, url):
		for t in range(10):
			try:
				page = urlopen(url)
				pagejson = page.read()
				return json.loads(pagejson.decode('utf-8'))
			except urllib.error.URLError:
				sleep(self.sleep_time_btw_queries)
		return None

	def _get_response_terms(self, response):
		if not response or 'query' not in response \
		or 'terms' not in list(response['query']['pages'].values())[0]:
			return []
		phrases = []
		for p,page in response['query']['pages'].items():
			if 'categories' in page:
				cat1 = page['categories'][0]['title']
				if re.search('[Dd]isambiguation', cat1):
					if page['extract']:
						phrases += self._get_extract_phrases(page['extract'], search_query=True)
				else: phrases += self._get_page_phrases(page)
		terms = []
		for phrase in phrases:
			phrase = phrase.strip()
			if phrase:
				main_part = re.split(' (%s) ' % self.regexps['preps'], phrase)[0]#.split()[-1]
				terms.append(re.sub('[.,?:;\\(\\)]', '', main_part))
		return terms

	def _get_extract_phrases(self, extract, search_query=False):
		phrases = []
		extract = html.fromstring(extract)
		extract_head = ''.join(extract.xpath('p//text()')).split('.')[0].strip()
		if re.match('[A-Z]+$', extract_head):
			return ['organization']
		extract_match = re.search(self.regexps['extract_prefs'], extract_head)
		if extract_match:
			if extract_match.end() < len(extract_head) - 2:
				phrases.append(extract_head[extract_match.end():])
			else: #if re.search('may refer to', extract_head):
				spans = extract.xpath('//span')
				if spans:
					first_id = spans[0].xpath('./@id')
					if first_id and re.match('Person|People|Place', first_id[0]):
						phrases.append(first_id[0])
		if search_query: #and not re.search('may refer to', extract_head):
			extract_lines = extract.xpath('//li//text()')
			for line in extract_lines:
				parens = re.search('\\((.+)\\)', line)
				if parens: phrases.append(parens.group(1))
				line_split = line.split(',')
				for part in line_split:
					if any(tok in self.regexps['dets'].split('|') for tok in part.split()):
						phrases.append(part)
						break
		return phrases

	def _get_page_phrases(self, page):
		phrases = [page['title']]
		if 'description' in page['terms']:
			for pt in page['terms']['description']:
				if not re.search(self.regexps['general_categs'], pt):
					phrases.append(pt)
		if 'label' in page['terms']:
			phrases += page['terms']['label']
		if 'alias' in page['terms']:
			phrases += page['terms']['alias']
		for pagecat in page['categories'][::-1]:
			cattext = pagecat['title'].split(':')[-1]
			if not re.search(self.regexps['general_categs'], cattext):
				phrases.append(cattext)
		if page['extract']:
			phrases += self._get_extract_phrases(page['extract'], search_query=False)
		return phrases

	def _get_first_synset(self, phrases):
		for phrase in phrases:
			phrase_parts = phrase.lower().split()
			prev_synset = ''
			for t in range(len(phrase_parts)):
				term = phrase_parts[t]
				if term in self.categ_synsets:
					synsets = [wn.synset(self.categ_synsets[term])]
				else: synsets = wn.synsets(term, 'n')
				if not synsets and term:
					synsets = wn.synsets(self.lemmatizer.lemmatize(term), 'n')
				#if not synsets and t > 0 and prev_synset:
				#	return prev_synset
				if synsets and len(term)>3:
					prev_synset = synsets[0].name()
			if prev_synset: return prev_synset
		return ''

	def _get_wiki_search_synset(self, term):
		url_term = urllib.parse.quote(term)
		url = self.url_base + '&list=search&srsearch=%s' % url_term
		response1 = self._get_wiki_response(url)
		if not response1['query']['search'] and 'searchinfo' in response1['query'] \
		and 'suggestion' in response1['query']['searchinfo']:
			url_term = urllib.parse.quote(response1['query']['searchinfo']['suggestion'])
			url = self.url_base + '&list=search&srsearch=%s' % url_term
			response1 = self._get_wiki_response(url)
		if response1['query']['search']:
			for result in response1['query']['search']:
				title = result['title']
				if self._title_close_enough(term, title):
					url_title = urllib.parse.quote(title)
					url = self.url_base + '&titles=%s&prop=categories|pageterms|extracts' % url_title
					response2 = self._get_wiki_response(url)
					rterms = self._get_response_terms(response2)
					synset = self._get_first_synset(rterms)
					if synset: return synset
		return ''

	def _title_close_enough(self, term, title):
		if re.match(term.lower(), title.lower()): return True
		if edit_distance(term.lower(), title.lower()) <= max(len(title),len(term)) / 2: return True
		if edit_distance(term.lower(), title.lower()) <= abs(len(title)-len(term)) + 1 \
		and len(term) >= len(title) / 3: return True
		return False

