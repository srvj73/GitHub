import sys, zipfile, collections
p = sys.argv[1]
z = zipfile.ZipFile(p)
names = z.namelist()
print("ENTRIES", len(names))
bad = [n for n in names if n.startswith('/') or '..' in n.replace('\\','/').split('/') or (len(n)>1 and n[1]==':')]
print("UNSAFE", bad)
c = collections.Counter(n.rstrip('/').lower() for n in names)
print("DUP", [k for k,v in c.items() if v>1])
tot = sum(i.file_size for i in z.infolist())
print("UNCOMPRESSED_TOTAL", tot)
for i in z.infolist()[:200]:
    print(f"{i.file_size:>12} {i.compress_type} {i.filename}")
print("TESTZIP", z.testzip())
