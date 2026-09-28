#!/usr/bin/env python3
import json, os, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

API="https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
ROOT=Path(__file__).resolve().parents[1]; SNAP=ROOT/"data"/"snapshots"
LATEST=ROOT/"data"/"latest.json"; CAND=ROOT/"data"/"candidates.json"

def fetch():
    app=os.environ.get("RAKUTEN_APPLICATION_ID"); key=os.environ.get("RAKUTEN_ACCESS_KEY")
    if not app or not key: raise SystemExit("Missing Rakuten API credentials")
    q=urllib.parse.urlencode({"applicationId":app,"accessKey":key,"format":"json","formatVersion":2})
    req=urllib.request.Request(API+"?"+q,headers={"User-Agent":"MITEKAU-ranking-history/1.0","Accept":"application/json","Referer":"https://nochamo.github.io/","Origin":"https://nochamo.github.io"})
    try:
        with urllib.request.urlopen(req,timeout=30) as r: return json.load(r)
    except urllib.error.HTTPError as e:
        body=e.read().decode("utf-8","replace")
        raise SystemExit(f"Rakuten API HTTP {e.code}: {body[:1000]}") from None

def normalize(raw,now):
    items=[]
    for x in raw.get("Items",raw.get("items",[])):
        x=x.get("Item",x)
        if not isinstance(x,dict): continue
        code=x.get("itemCode"); rank=x.get("rank")
        if not code or rank is None: continue
        try: rank=int(rank)
        except (TypeError,ValueError): continue
        items.append({k:v for k,v in {
          "itemCode":code,"rank":rank,"itemName":x.get("itemName"),"itemPrice":x.get("itemPrice"),
          "reviewAverage":x.get("reviewAverage"),"reviewCount":x.get("reviewCount"),
          "itemUrl":x.get("itemUrl"),"affiliateUrl":x.get("affiliateUrl")}.items()})
    return {"schemaVersion":1,"source":"Rakuten Ichiba Item Ranking API 2022-06-01",
      "fetchedAt":now.isoformat(),"lastBuildDate":raw.get("lastBuildDate"),"count":len(items),"items":items}

def history():
    out=[]
    for p in SNAP.glob("*.json"):
        try:
            d=json.loads(p.read_text(encoding="utf-8")); t=datetime.fromisoformat(d["fetchedAt"].replace("Z","+00:00")); out.append((t,d))
        except Exception: pass
    return sorted(out,key=lambda z:z[0])

def nearest(hist,now,hours,tolerance):
    target=hours*3600; c=[]
    for t,d in hist:
        age=(now-t).total_seconds()
        if age>0 and abs(age-target)<=tolerance*3600: c.append((abs(age-target),d))
    return min(c,key=lambda z:z[0])[1] if c else None

def ranks(d): return {x["itemCode"]:x["rank"] for x in d.get("items",[])} if d else {}

def analyze(cur,hist,now):
    h4=nearest(hist,now,4,2); h24=nearest(hist,now,24,3); r4=ranks(h4); r24=ranks(h24)
    recent=[d for t,d in hist if 0<(now-t).total_seconds()<=26*3600]; out=[]
    for x in cur["items"]:
        code=x["itemCode"]; rank=x["rank"]; d4=r4.get(code)-rank if code in r4 else None; d24=r24.get(code)-rank if code in r24 else None
        seen=[ranks(d).get(code) for d in recent]; seen=[v for v in seen if v is not None]
        rising=rank<=100 and ((d4 is not None and d4>=10) or (d24 is not None and d24>=25))
        proven=rank<=50 and len(seen)>=4 and max(seen+[rank])<=100
        if rising or proven:
            y=dict(x); y.update({"change4h":d4,"change24h":d24,"observations24h":len(seen)+1,
              "labels":(["RISING"] if rising else [])+(["PROVEN"] if proven else [])}); out.append(y)
    out.sort(key=lambda x:(0 if "RISING" in x["labels"] else 1,x["rank"]))
    return {"schemaVersion":1,"generatedAt":now.isoformat(),
      "comparison":{"4h":{"status":"OK" if h4 else "INSUFFICIENT_HISTORY","snapshotAt":h4.get("fetchedAt") if h4 else None},
                    "24h":{"status":"OK" if h24 else "INSUFFICIENT_HISTORY","snapshotAt":h24.get("fetchedAt") if h24 else None}},
      "rules":{"RISING":"rank<=100 and (4h rise>=10 or 24h rise>=25)",
               "PROVEN":"rank<=50 and >=4 prior observations in ~24h and rank stayed<=100"},"candidates":out}

def main():
    now=datetime.now(timezone.utc); SNAP.mkdir(parents=True,exist_ok=True); hist=history(); cur=normalize(fetch(),now)
    if cur["count"]==0: raise SystemExit("Ranking API returned zero usable items; refusing empty snapshot")
    p=SNAP/(now.strftime("%Y%m%dT%H%M%SZ")+".json"); p.write_text(json.dumps(cur,ensure_ascii=False,indent=2),encoding="utf-8")
    LATEST.write_text(json.dumps(cur,ensure_ascii=False,indent=2),encoding="utf-8")
    CAND.write_text(json.dumps(analyze(cur,hist,now),ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"saved {p.name}: {cur['count']} items")
if __name__=="__main__": main()
