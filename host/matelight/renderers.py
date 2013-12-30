import time
try:
	import re2 as re
except ImportError:
	import re
import numpy as np
from PIL import Image
from pixelterm import xtermcolors
from config import *
from font import *

default_palette = [
		(0x00, 0x00, 0x00), # 0 normal colors
		(0xcd, 0x00, 0x00), # 1
		(0x00, 0xcd, 0x00), # 2
		(0xcd, 0xcd, 0x00), # 3
		(0x00, 0x00, 0xee), # 4
		(0xcd, 0x00, 0xcd), # 5
		(0x00, 0xcd, 0xcd), # 6
		(0xe5, 0xe5, 0xe5), # 7
		(0x7f, 0x7f, 0x7f), # 8 bright colors
		(0xff, 0x00, 0x00), # 9
		(0x00, 0xff, 0x00), # 10
		(0xff, 0xff, 0x00), # 11
		(0x5c, 0x5c, 0xff), # 12
		(0xff, 0x00, 0xff), # 13
		(0x00, 0xff, 0xff), # 14
		(0xff, 0xff, 0xff)] # 15
default_colors = (default_palette[8], default_palette[0])

class CharGenerator:
	def __init__(self, seq=None, lg=None, text=''):
		settings = False, False, False, default_colors
		if lg:
			settings = lg.bold, lg.blink, lg.underscore, (lg.fg, lg.bg)
		self.bold, self.blink, self.underscore, (self.fg, self.bg) = settings
		self.text = text
		if seq:
			self.parse_escape_sequence(seq)

	def parse_escape_sequence(self, seq):
		codes = list(map(int, seq[2:-1].split(';')))
		fg, bg, reverse, i = self.fg, self.bg, False, 0
		while i<len(codes):
			a = codes[i]
			if a in [38, 48]:
				if codes[i+1] == 5:
					c = xtermcolors.xterm_colors[codes[i+2]]
					fg, bg = (c, bg) if a == 38 else (fg, c)
					i += 2
			elif a == 39:
				fg = (0,0,0)
			elif a == 49:
				bg = (0,0,0)
			elif a == 0:
				fg, bg = default_colors
				self.bold, self.blink, self.underscore = False, False, False
			elif a in range(30, 38):
				fg = default_palette[a-30]
			elif a in range(90, 98):
				fg = default_palette[a-90+8]
			elif a in range(40, 48):
				bg = default_palette[a-40]
			elif a in range(101, 108):
				bg = default_palette[a-100+8]
			elif a == 7:
				reverse = True
			elif a == 5:
				self.blink = True
			elif a == 4:
				self.underscore = True
			elif a == 1: # Literally "bright", not bold.
				self.bold = True
			i += 1
		fg, bg = (bg, fg) if reverse else (fg, bg)
		self.fg, self.bg = fg, bg

	def generate_char(self, c, now):
		fg, bg = (self.bg, self.fg) if self.blink and now%1.0 < 0.3 else (self.fg, self.bg)
		glyph = FONT.glyphs_by_codepoint[ord(c)]
		# Please forgive the string manipulation below.
		lookup = {'0': bg, '1': fg}
		FONT_PADDED_BINARY = ('{:0'+str(glyph.bbW)+'b}').format
		FONT_Y_PAD = [[bg]*glyph.bbW]*(DISPLAY_HEIGHT-FONT_HEIGHT)
		return np.swapaxes(np.array([ list(map(lookup.get, FONT_PADDED_BINARY(int(row, 16))[:glyph.bbW])) for row in glyph.get_data() ] + FONT_Y_PAD, dtype=np.uint8), 0, 1)

	def generate(self, now):
		chars = [self.generate_char(c, now) for c in self.text]
		# This refers to inter-letter spacing
		space = np.zeros((LETTER_SPACING, DISPLAY_HEIGHT, 3), dtype=np.uint8)
		spaces = [space]*(len(chars)-1)
		everything = chars + spaces
		everything[::2] = chars
		everything[1::2] = spaces
		return np.concatenate(everything)

class TextRenderer:
	def __init__(self, text, escapes=True):
		"""Renders text into a frame buffer

		"escapes" tells the renderer whether to interpret escape sequences (True) or not (False).
		"""
		generators = []
		current_generator = CharGenerator()
		for match in re.finditer('(\x1B\[[0-9;]+m)|(.)', text):
			esc, char = match.groups()
			if esc:
				if current_generator.text != '':
					generators.append(current_generator)
				current_generator = CharGenerator(esc, current_generator)
			elif char:
				current_generator.text += char
		generators = generators + [current_generator]
		# Generate the actual frame buffer
		zeros = [np.zeros((DISPLAY_WIDTH, DISPLAY_HEIGHT, 3), dtype=np.uint8)]
		# Pad the array with one screen's worth of zeros on both sides so the text fully scrolls through.
		now = time.time()
		self.raw = np.concatenate(zeros+[g.generate(now) for g in generators]+zeros)

	def frames(self):
		w,h,_ = self.raw.shape
		for i in range(0, w-DISPLAY_WIDTH, 2):
			frame = self.raw[i:i+DISPLAY_WIDTH, :, :]
			yield frame, 1/DEFAULT_SCROLL_SPEED

class ImageRenderer:
	def __new__(cls, image_data):
		img = Image.open(io.BytesIO(image_data))
		self.img = img

	def frames(self):
		img = self.img
		palette = img.getpalette()
		last_frame = Image.new("RGB", img.size)
		# FIXME set delay to 1/10s if the image is animated, only use DEFAULT_IMAGE_DURATION for static images.
		delay = img.info.get('duration', DEFAULT_IMAGE_DURATION*1000.0)/1000.0

		for frame in ImageSequence.Iterator(img):
			#This works around a known bug in Pillow
			#See also: http://stackoverflow.com/questions/4904940/python-converting-gif-frames-to-png
			frame.putpalette(palette)
			c = frame.convert("RGB")

			if img.info['background'] != img.info['transparency']:
				last_frame.paste(c, c)
			else:
				last_frame = c

			im = last_frame.copy()
			im.thumbnail((DISPLAY_WIDTH, DISPLAY_HEIGHT), Image.NEAREST)
			data = np.array(im.getdata(), dtype=np.int8)
			data.reshape((DISPLAY_WIDTH, DISPLAY_HEIGHT, 3))
			yield data, delay
