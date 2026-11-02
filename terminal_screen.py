"""Small VT screen reader for ab-av1's line-oriented terminal output."""
import json
import re


class Screen:
    def __init__(self, columns=180, rows=35):
        self.columns, self.height = columns, rows
        self.lines = [''] * rows
        self.row = self.col = 0
        self.pending = ''
        self.previous = set()
        self.results = set()

    def feed(self, text):
        self.pending += text
        i = 0
        while i < len(self.pending):
            c = self.pending[i]
            if c == '\x1b':
                if i + 1 >= len(self.pending): break
                if self.pending[i + 1] == '[':
                    match = re.match(r'\x1b\[([0-?]*)([ -/]*)([@-~])', self.pending[i:])
                    if not match: break
                    raw, _, op = match.groups()
                    numbers = [int(n) if n.isdigit() else 0 for n in raw.lstrip('?').split(';')]
                    n = numbers[0] or 1
                    if op in 'Hf': self.row, self.col = min(self.height-1, n-1), max(0, (numbers[1] if len(numbers)>1 else 1)-1)
                    elif op == 'A': self.row = max(0, self.row-n)
                    elif op == 'B': self.row = min(self.height-1, self.row+n)
                    elif op == 'C': self.col = min(self.columns-1, self.col+n)
                    elif op == 'D': self.col = max(0, self.col-n)
                    elif op == 'G': self.col = max(0, n-1)
                    elif op == 'K':
                        mode = numbers[0]
                        self.lines[self.row] = '' if mode == 2 else self.lines[self.row][:self.col] if mode == 0 else ' '*self.col+self.lines[self.row][self.col:]
                    elif op == 'J' and numbers[0] in [2,3]: self.lines = ['']*self.height
                    i += len(match[0]); continue
                if self.pending[i + 1] == ']':
                    end = re.search(r'\x07|\x1b\\', self.pending[i+2:])
                    if not end: break
                    i += 2 + end.end(); continue
                i += 2; continue
            if c == '\r': self.col = 0
            elif c == '\n': self.newline()
            elif c == '\b': self.col = max(0,self.col-1)
            elif c >= ' ':
                if self.col >= self.columns: self.col=0; self.newline()
                line=self.lines[self.row].ljust(self.col)
                self.lines[self.row]=line[:self.col]+c+line[self.col+1:]
                self.col+=1
            i += 1
        self.pending=self.pending[i:]
        output=[]
        joined=''.join(self.lines)
        decoder=json.JSONDecoder()
        for match in re.finditer(r'\{',joined):
            try:
                event,_=decoder.raw_decode(joined[match.start():])
                if not isinstance(event,dict) or 'type' not in event: continue
                encoded=json.dumps(event,sort_keys=True)
                if encoded not in self.results:
                    self.results.add(encoded);output.append(('stdout',encoded))
            except ValueError: pass
        current={line.strip() for line in self.lines if line.strip() and not line.lstrip().startswith(('{','"'))}
        for line in dict.fromkeys(line.strip() for line in self.lines if line.strip()):
            if line in self.previous: continue
            if 'type":' not in line and 'predicted_encode_' not in line: output.append(('stderr',line))
        self.previous=current
        return output

    def newline(self):
        self.row += 1
        if self.row >= self.height:
            self.lines.pop(0);self.lines.append('');self.row=self.height-1
