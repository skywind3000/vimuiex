#!/usr/bin/env python
# vim:set fileencoding=utf-8 sw=4 ts=8 et:vim
# popuplist.py - a generic listing facility with popup listboxes
#
# Author: Marko Mahnič
# Created: April 2009
# License: GPL (http://www.gnu.org/copyleft/gpl.html)
# This program comes with ABSOLUTELY NO WARRANTY.

import time
import vim
import simplekeymap
import ioutil

# TODO: vimuiex init script when the list is used for the first time: copy vars from vim to python
BORDER = (2, 2) # Drawing errors in curses when w > &columns-12
# import the correct listbox implementation
__listbox = None
def importListboxImpl():
    global __listbox, BORDER
    if __listbox != None: return __listbox
    if ioutil.PLATFORM == "vim.screen":
        import vimuiex._popuplist_screen as __listbox
        BORDER = (2, 2)
    elif ioutil.PLATFORM == "curses":
        import vimuiex._popuplist_screen as __listbox #TODO: Unify in _screen
        BORDER = (12, 4) # Drawing errors in curses when w > &columns-12
    elif ioutil.PLATFORM == "wx":
        import vimuiex._popuplist_wx as __listbox
        BORDER = (2, 2)
    else:
        raise SystemError("VimUiEx: Invalid platform")

    return __listbox

def log(msg):
    f = open ("testlog.txt", "a")
    f.write(msg + "\n")
    f.close()

def vimScreenSize():
    return (int(vim.eval("&columns")), int(vim.eval("&lines")))

class CListItem(object):
    def __init__(self, text=""):
        self.flags = 0
        self._text = text
        self.quickchar = None
        self.selected = 0

    @property
    def displayText(self):
        return self._text

    @property
    def filterText(self):
        return self._text

# TODO: add incremental search: works like filter, but lines are not hidden;
#       TAB moves to next occurence; needed eg. with VxMan;
# TODO: add default search mode for /: i-search or filter
# TODO: implement multiline list items (eg. up to 3 lines)
# TODO: pack listbox positioning in a separate class
class CList(object):
    def __init__(self, title="", position=None, align=None, size=None, autosize=None):
        """
        position: (x, y); if None, center the listbox
        align:    alignment string (eg. "TL", "BR", "T", ...); overrides position
        size:     (width, height); if None, half of screen size in each direction
        autosize: autosize string (eg. "V", "H", "C", "VH")
                  V - autosize vertically
                  H - autosize horizontally
                  C - autosize 1st column (tab delimited)
        """
        if title != None: self.title = title
        else: self.title = ""
        self.titleAlign = "<"
        self.position = position
        self.align = align
        self.size = size
        self.minSize = (16, 4)
        self.autosize = autosize
        self._firstColumnWidth = None # property: Width of the first column
        self.maxColumnWidth = 0.3
        self.allitems = []
        self.strFilter = "" 
        self.__items = None     # Displayed (filtered) items; delayed creation in items()
        self.__listbox = None   # Listbox implementation
        self.sort = True        # sort input list
        self.filtersort = True  # sort filterd data (quickchar, startswith, contains)
        self.keymapNorm = simplekeymap.CSimpleKeymap()
        self.keymapFilter = simplekeymap.CSimpleKeymap()
        self.keymapQuickChar = simplekeymap.CSimpleKeymap()
        self.keymapNumSelect = simplekeymap.CSimpleKeymap()
        self.quickCharAutoSelect = "accept" # An item with a unique quick char will be auto-"accept"-ed; TODO: make it nicer
        self.cmdCancel = "" # 'echo "canceled"'
        self.cmdAccept = "" # 'echo "accepted {{i}}"'
        self.initKeymaps()

    def getTitle(self, maxwidth):
        if len(self.title) < maxwidth: return self.title
        if maxwidth > 12:
            maxwidth -= 3
            dots = "..."
        else: dots = ""
        if self.titleAlign == ">": return dots + self.title[-maxwidth:]
        return self.title[:maxwidth] + dots

    def getExtraPrompt(self, maxwidth=40):
        return ""

    def initKeymaps(self):
        def addCursorMoves(kn):
            kn.setKey(r"\<down>", "next")
            kn.setKey(r"\<up>", "prev")
            kn.setKey(r"\<left>", "lshift")
            kn.setKey(r"\<right>", "rshift")
            kn.setKey(r"\<pagedown>", "nextpage")
            kn.setKey(r"\<pageup>", "prevpage")
            kn.setKey(r"\<home>", "home")
            kn.setKey(r"\<end>", "end")
            # TODO: Experimental
            kn.setKey(r"\<TAB>", "next")
            kn.setKey(r"\<S-TAB>", "prev")
        kn = self.keymapNorm
        addCursorMoves(kn)
        kn.setKey(r"j", "next")
        kn.setKey(r"k", "prev")
        kn.setKey(r"h", "lshift")
        kn.setKey(r"l", "rshift")
        kn.setKey(r" ", "nextpage")
        kn.setKey(r"b", "prevpage")
        kn.setKey(r"n", "nextpage") # MAYBE: remove mapping
        kn.setKey(r"p", "prevpage") # MAYBE: remove mapping
        kn.setKey(r"0", "home") # MAYBE: set offset to 0
        kn.setKey(r"gg", "home")
        kn.setKey(r"$", "end") # MAYBE: set offset to view the end of the longest line
        kn.setKey(r"G", "end")
        kn.setKey(r"f", "filter")
        kn.setKey(r"/", "filter")
        kn.setKey(r"&", "quickchar")
        kn.setKey(r"i", "numselect")
        kn.setKey(r"#", "numselect")
        kn.setKey(r"q", "quit")
        kn.setKey(r"\<Esc>", "quit")
        kn.setKey(r"\<CR>", "accept")
        kn.setKey(r"wk", "winpos:align-top")
        kn.setKey(r"wj", "winpos:align-bottom")
        kn.setKey(r"wh", "winpos:align-left")
        kn.setKey(r"wl", "winpos:align-right")
        kn.setKey(r"wc", "winpos:align-hceneter")
        kn.setKey(r"wv", "winpos:align-vceneter")
        kn.setKey(r"wC", "winpos:align-ceneter")
        kn = self.keymapFilter
        addCursorMoves(kn)
        kn.setKey(r"\<CR>", "filter-accept")
        kn.setKey(r"\<ESC>", "filter-cancel")
        kn.setKey(r"\<BS>", "filter-delete")
        kn.setKey(r"\<TAB>", "filter-next")
        kn.setKey(r"\<S-TAB>", "filter-prev")
        kn = self.keymapQuickChar
        addCursorMoves(kn)
        kn.setKey(r"\<CR>", "accept")
        kn.setKey(r"\<ESC>", "quit")
        kn.setKey(r"&", "exit-quickchar")
        kn.setKey(r"/", "filter")
        kn.setKey(r"#", "numselect")
        kn = self.keymapNumSelect
        kn.setKey(r"\<CR>", "accept")
        kn.setKey(r"\<ESC>", "quit")
        kn.setKey(r"\<BS>", "numselect-delete")
        kn.setKey(r"q", "quit")
        kn.setKey(r"&", "quickchar")
        kn.setKey(r"/", "filter")

    # TODO: 3. python: eval a python command
    def doCommand(self, cmd, curindex):
        if cmd.startswith("list:"): cmd = self.doListCommand(cmd[5:].strip(), curindex)
        elif cmd.startswith("winpos:"):
            self.doWinposCmd(cmd[7:].strip())
            cmd = ""
        elif cmd.startswith("vim:"): return "" # TODO
        return cmd

    def doWinposCmd(self, cmd):
        def _realign(remove, add):
            if self.align == None: align = ""
            else: align = self.align.lower()
            if remove != None:
                for ch in remove: align = align.replace(ch, "")
            if add != None: align += add
            self.align = align
            self.relayout(position=True, size=False)
        if cmd == "align-left": _realign("r", "l")
        elif cmd == "align-right": _realign("l", "r")
        elif cmd == "align-top": _realign("b", "t")
        elif cmd == "align-bottom": _realign("t", "b")
        elif cmd == "align-hceneter": _realign("lr", "")
        elif cmd == "align-vceneter": _realign("tb", "")
        elif cmd == "align-ceneter": _realign("lrtb", "")

    def doListCommand(self, cmd, curindex):
        return cmd

    def redraw(self):
        if self.__listbox != None: self.__listbox.redraw()

    def refreshDisplay(self):
        self.__items = None
        self._firstColumnWidth = None
        if self.__listbox != None: self.__listbox.refreshDisplay()

    def setFilter(self, strFilter = ""):
        if strFilter == self.strFilter: return
        self.strFilter = strFilter
        self.refreshDisplay()

    def setCurIndex(self, index):
        if self.__listbox == None: return
        self.__listbox.setCurIndex(index)
        pass

    @property
    def items(self):
        if self.__items == None: self.__applyFilter()
        return self.__items

    @property
    def itemCount(self):
        if self.__items == None: self.__applyFilter()
        return len(self.__items)

    def __applyFilter(self):
        if self.strFilter == None or self.strFilter == "":
            self.__items = [i for i in self.allitems]
        else:
            filt = self.strFilter.lower()
            startat = 0
            inhead=[]; intail=[]
            for i in self.allitems:
                pos = i.filterText.lower().find(filt, startat)
                if pos < 0: continue
                elif pos == startat and self.filtersort: inhead.append(i)
                else: intail.append(i)
            self.__items = inhead + intail
        pass

    def loadBufferItems(self, bufnum, minline = 0, maxline = -1):
        buf = vim.buffers[bufnum-1]
        a, b = 0, len(buf)
        # TODO: minline, maxline
        # TODO: fileencoding/encoding for buf
        self.allitems = [CListItem(line) for line in buf[a:b]]
        self.refreshDisplay()

    def loadVimItems(self, vimvar):
        encoding = vim.eval("&encoding")
        self.allitems = [CListItem(line.decode(encoding)) for line in vim.eval(vimvar)]
        self.refreshDisplay()

    def loadUnicodeItems(self, pylist):
        # TODO: convert to unicode
        self.allitems = [CListItem(line) for line in pylist]
        self.refreshDisplay()
    
    def loadTestItems(self):
        self.allitems = [CListItem(i) for i in [u"one"*14, u"two"*13, u"three"*12, u"four"*11] * 10]
        self.refreshDisplay()

    def getTrueIndex(self, filteredIndex):
        if self.__items != None: nitems = len(self.__items)
        else: nitems = 0
        if filteredIndex < 0 or filteredIndex >= nitems: i = -1
        else: i = self.allitems.index(self.__items[filteredIndex])
        return i

    def expandVimCommand(self, command, curindex):
        i = self.getTrueIndex(curindex)
        return command.replace("{{i}}", "%d" % (i))
        pass

    def _maxSize(self):
        (w, h) = vimScreenSize()
        w -= BORDER[0];
        h -= BORDER[1];
        return (w, h)

    def _limitSize(self, sx, sy):
        w, h = self._maxSize()
        if self.minSize[0] > w: self.minSize[0] = w
        if self.minSize[1] > h: self.minSize[1] = h
        if sx < self.minSize[0]: sx = self.minSize[0]
        if sy < self.minSize[1]: sy = self.minSize[1]
        if sx > w: sx = w
        if sy > h: sy = h
        return (sx, sy)

    def _limitPosition(self, x, y, size=None):
        w, h = self._maxSize()
        if size == None: sx, sy = self.size
        else: sx, sy = size
        l = BORDER[0] / 2
        t = BORDER[1] / 2
        if x < l: x = l
        if y < t: y = t
        if x - l + sx > w: x = w - sx + l
        if y - t + sy > h: y = h - sy + l
        return (x, y)
    
    def calcFirstColumnWidth(self, textwidth, items):
        mwf = self.maxColumnWidth
        if mwf < 0.2: mwf = 0.2
        if mwf > 0.8: mwf = 0.8
        wmax = int(textwidth * mwf)
        wopt = 0
        for i in items:
            if i.displayText.find("\t") < 0: continue
            cols = i.displayText.split("\t", 1)
            w = len(cols[0].rstrip())
            if w > wopt: wopt = w
            if wopt > wmax: wopt = wmax; break
        return wopt

    def getFirstColumnWidth(self, textwidth=None):
        if self.autosize.lower().find("c") < 0: return None
        if self._firstColumnWidth != None: return self._firstColumnWidth
        if textwidth == None or textwidth < 1: textwidth = self.size[0]
        wopt = self.calcFirstColumnWidth(textwidth, self.items)
        if wopt > 0: self._firstColumnWidth = wopt
        return self._firstColumnWidth

    def relayout(self, position=True, size=True):
        w, h = self._maxSize()
        if size and self.autosize != None:
            sx, sy = self.size
            autosize = self.autosize.lower()
            if autosize.find("v") >= 0: sy = len(self.allitems) + 2
            if autosize.find("h") >= 0:
                if len(self.allitems) < 1: sx = 0
                else: sx = max([len(li.displayText) for li in self.allitems]) + 2
            self.size = self._limitSize(sx, sy)

        if position and self.align != None:
            x, y = self.position
            l = BORDER[0] / 2
            t = BORDER[1] / 2
            align = self.align.lower()
            if align.find("t") >= 0: y = t
            elif align.find("b") >= 0: y = h - self.size[1] + t
            else: y = (h - self.size[1]) / 2
            if align.find("l") >= 0: x = l
            elif align.find("r") >= 0: x = w - self.size[0] + l
            else: x = (w - self.size[0]) / 2
            self.position = self._limitPosition(x, y)

        if self.__listbox != None:
            self.__listbox.relayout(self.position, self.size)

    def _calcInitialPosition(self):
        w, h = self._maxSize()
        if self.size == None: self.size = (w/2, h/2)
        l = BORDER[0] / 2
        t = BORDER[1] / 2
        if self.position == None: self.position = (l + w/4, t + h/4)
        self.relayout()

    def process(self, curindex = 0, startmode = 1): # TODO: startmode=sth.NORMAL
        lbimpl = importListboxImpl()
        if lbimpl == None: return
        self._calcInitialPosition()
	self.__listbox = lbimpl.createListboxView(position=self.position, size=self.size)
	self.__listbox.setItemList(self)
	exitcmd = self.__listbox.process(curindex, startmode)
        # WX: will exit immediately; non-modal window
        # Curses: will exit after processing and return the exit command (modal window)
        if exitcmd != None:
            cmd = None
            if exitcmd[0] == "accept": cmd = self.cmdAccept
            elif exitcmd[0] == "quit": cmd = self.cmdCancel
            if cmd != None:
                import inspect
                idx = exitcmd[1]
                if inspect.isfunction(cmd): cmd(self.getTrueIndex(idx))
                elif type(cmd) == type("") and cmd != "":
                    cmd = self.expandVimCommand(cmd, idx)
                    vim.command(cmd)

