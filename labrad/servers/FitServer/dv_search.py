import labrad
import re

def dv_search(data_vault,regex,path=[""]):
    dv = data_vault.packet()
    dv.cd(path)
    dv.dir(key="contents")
    ans = dv.send()

    contents = ans.contents

    for f in contents[1]:
        if regex.match(f):
            yield (path,f)
            
    for d in contents[0]:
        path.append(d)
        for q in dv_search(data_vault,regex,path):
            yield q
        path.pop()
