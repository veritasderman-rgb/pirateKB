import zipfile, os
DOC={'.pdf','.docx','.odt','.xlsx','.ods','.md','.txt','.doc','.pptx','.odp','.csv','.rtf','.tsv','.html','.xls','.json','.vtt','.srt','.odg'}
z=zipfile.ZipFile("D:/Data/Mrak/Centrala.zip"); n=0; tot=0
for i in z.infolist():
    if i.is_dir(): continue
    if os.path.splitext(i.filename)[1].lower() not in DOC: continue
    if i.file_size>200*1024*1024: print("skip big",i.filename,i.file_size); continue
    z.extract(i,"D:/Data/Mrak/Centrala"); n+=1; tot+=i.file_size
print(n, tot/1e9,"GB")
