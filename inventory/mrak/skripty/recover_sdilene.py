import json, os, struct
SRC="D:/Data/Mrak/Sdílené.zip"; OUT="D:/Data/Mrak/Sdílené"
hits=json.load(open(os.path.join(os.path.dirname(__file__),"sdilene_hits.json")))
sz=os.path.getsize(SRC)
DOC={'.pdf','.docx','.odt','.xlsx','.ods','.md','.txt','.doc','.pptx','.odp','.csv','.rtf'}
f=open(SRC,"rb"); n=0
for k,(off,_,flag,meth) in enumerate(hits):
    f.seek(off); h=f.read(30)
    nl,el=struct.unpack("<HH",h[26:30]); name=f.read(nl).decode('utf-8'); 
    if name.endswith('/'): continue
    ext=os.path.splitext(name)[1].lower()
    if ext not in DOC: continue
    start=off+30+nl+el
    end=hits[k+1][0] if k+1<len(hits) else None
    if end is None:
        # last entry: find EOCD of xlsx (PK\x05\x06) then +22
        f.seek(start); buf=f.read(sz-start); i=buf.rfind(b'PK\x05\x06'); end=start+i+22
    else:
        f.seek(end-24); d=f.read(24)
        if d[:4]==b'PK\x07\x08': end-=24
        else:
            f.seek(end-16); d=f.read(16)
            if d[:4]==b'PK\x07\x08': end-=16
    p=os.path.join(OUT,name); os.makedirs(os.path.dirname(p),exist_ok=True)
    f.seek(start); open(p,"wb").write(f.read(end-start)); n+=1
print("recovered",n)
