"""Exercise the actual native result reader, including no-follow/nonblocking IO."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class NativeResultIO(unittest.TestCase):
    def test_regular_control_symlink_fifo_directory_and_oversized_metadata(self):
        source=Path(__file__).with_name('Main.swift').read_text()
        helper=source[source.index('func readResultJSON('):source.index('\nimport UniformTypeIdentifiers')]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'result';folder.mkdir()
            (folder/'good.json').write_text('{"status":"complete"}')
            (root/'outside.json').write_text('{"status":"complete"}')
            for name in ('run_manifest.json','validation.json'):(folder/name).symlink_to(root/'outside.json')
            os.mkfifo(folder/'pipe.json');(folder/'directory.json').mkdir()
            with (folder/'large.json').open('wb') as f:f.truncate((128<<20)+1)
            (root/'results').symlink_to(folder,target_is_directory=True)
            tests=r'''
let root=URL(fileURLWithPath:CommandLine.arguments[1])
let folder=root.appendingPathComponent("result")
guard try readResultJSON(folder,"good.json")?["status"] as? String == "complete" else { fatalError("regular control") }
var checks=1
for name in ["run_manifest.json","validation.json","pipe.json","directory.json","large.json"] {
    do { _ = try readResultJSON(folder,name); fatalError("accepted unsafe metadata: \(name)") }
    catch { checks += 1 }
}
do { _ = try readResultJSON(root.appendingPathComponent("results"),"good.json"); fatalError("followed result directory symlink") }
catch { checks += 1 }
print("{\"checks\":\(checks)}")
'''
            swift=root/'check.swift';swift.write_text('import Foundation\nimport Darwin\n'+helper+tests)
            binary=root/'check'
            subprocess.run(['xcrun','swiftc','-module-cache-path',str(root/'cache'),str(swift),'-o',str(binary)],check=True,capture_output=True,timeout=60)
            result=subprocess.run([str(binary),str(root)],check=True,capture_output=True,text=True,timeout=10)
            self.assertEqual(json.loads(result.stdout)['checks'],7)


if __name__=='__main__':unittest.main()
