"""Exercise Main.swift's LineBuffer: correct splitting across arbitrary chunks and linear time on huge lines."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(sys.platform == 'darwin', 'compiles a helper of the macOS shell')
class LineBufferTest(unittest.TestCase):
    def test_split_correctness_and_large_line_performance(self):
        source=Path(__file__).with_name('Main.swift').read_text()
        helper=source[source.index('struct LineBuffer {'):source.index('/// A backend task is finished')]
        checks=r'''
var buffer=LineBuffer()
var lines:[String]=[]
for chunk in ["{\"a\"", ":1}\n{\"b\":2}\n\n{\"c\"", ":3", "}\n"] { lines += buffer.append(chunk.data(using:.utf8)!).map { String(data:$0,encoding:.utf8)! } }
guard lines == ["{\"a\":1}","{\"b\":2}","","{\"c\":3}"] else { fatalError("split: \(lines)") }
var big=LineBuffer(); var huge=Data(repeating:65,count:50_000_000); huge.append(10); huge.append(contentsOf:[66,10])
let start=Date(); var found:[Int]=[]; var offset=0
while offset<huge.count { let end=min(offset+65536,huge.count); found += big.append(huge.subdata(in:offset..<end)).map { $0.count }; offset=end }
guard found == [50_000_000,1] else { fatalError("big: \(found)") }
print("{\"seconds\":\(Date().timeIntervalSince(start))}")
'''
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);swift=root/'check.swift';swift.write_text('import Foundation\nimport Darwin\n'+helper+checks)
            subprocess.run(['xcrun','swiftc','-O','-module-cache-path',str(root/'cache'),str(swift),'-o',str(root/'check')],check=True,capture_output=True,timeout=120)
            result=subprocess.run([str(root/'check')],check=True,capture_output=True,text=True,timeout=60)
            self.assertLess(json.loads(result.stdout)['seconds'],5)   # v1.3's rescanning took minutes at this size


if __name__=='__main__':unittest.main()
