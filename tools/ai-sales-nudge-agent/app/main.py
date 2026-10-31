from contextlib import asynccontextmanager, contextmanager
import os
import sqlite3
import uuid
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

ROOT=Path(__file__).resolve().parents[1]
DB=Path(os.getenv('NUDGE_DB',str(ROOT/'instance/nudges.db')))
@asynccontextmanager
async def lifespan(app: FastAPI):
 init()
 yield

app=FastAPI(title='Sales Follow-up Prioritizer',version='0.1.0',lifespan=lifespan)
LEADS=[{'id':'SYN-LEAD-01','name':'Asha','stage':'evaluation','days_since_contact':12,'engagement_14d':1,'next_step':'share implementation checklist'}, {'id':'SYN-LEAD-02','name':'Ravi','stage':'discovery','days_since_contact':3,'engagement_14d':5,'next_step':'confirm team requirements'}, {'id':'SYN-LEAD-03','name':'Meera','stage':'proposal','days_since_contact':21,'engagement_14d':0,'next_step':'offer a proposal review'}]

@contextmanager
def dbconn():
 DB.parent.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(DB)
 try:
  yield c;c.commit()
 except Exception:c.rollback();raise
 finally:c.close()

def init():
 with dbconn() as c:c.execute('CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY,lead_id TEXT NOT NULL,message TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,approved_at TEXT)')

def recommend(lead):
 score=min(100,lead['days_since_contact']*3 + max(0,3-lead['engagement_14d'])*8 + (15 if lead['stage']=='proposal' else 0))
 priority='review-soon' if score>=55 else 'normal'
 message=f"Hi {lead['name']}, would it help if I {lead['next_step']}? Happy to work around your timeline."
 return {'lead_id':lead['id'],'priority':priority,'score':score,'reason':'Rule-based recency and engagement signal; verify CRM context before use.','draft_message':message,'status':'DRAFT_ONLY'}

class Draft(BaseModel):lead_id:str=Field(min_length=1,max_length=50);message:str=Field(min_length=10,max_length=1000)

@app.get('/health')
def health():return {'status':'ok'}

@app.get('/api/leads')
def leads():return {'items':[recommend(x) for x in LEADS]}

@app.post('/api/drafts')
def save_draft(payload:Draft):
 if payload.lead_id not in {l['id'] for l in LEADS}:raise HTTPException(404,'Synthetic lead not found.')
 draft_id=str(uuid.uuid4())
 with dbconn() as c:c.execute("INSERT INTO drafts(id,lead_id,message,status) VALUES(?,?,?,'NEEDS_APPROVAL')",(draft_id,payload.lead_id,payload.message))
 return {'draft_id':draft_id,'status':'NEEDS_APPROVAL','notice':'No message was sent.'}

@app.post('/api/drafts/{draft_id}/approve')
def approve(draft_id:str):
 with dbconn() as c:
  cur=c.execute("UPDATE drafts SET status='APPROVED',approved_at=CURRENT_TIMESTAMP WHERE id=? AND status='NEEDS_APPROVAL'",(draft_id,))
  if cur.rowcount!=1:raise HTTPException(404,'Pending draft not found.')
 return {'draft_id':draft_id,'status':'APPROVED','notice':'Local approval recorded. Sending is not implemented.'}

@app.get('/',response_class=HTMLResponse)
def home():return """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Sales Follow-up Prioritizer</title><style>body{font:16px system-ui;max-width:850px;margin:3rem auto;padding:0 1rem}button{padding:.6rem;background:#164e63;color:white;border:0;border-radius:5px}article{padding:1rem;border:1px solid #ccd5dc;margin:.7rem 0}</style></head><body><h1>Sales Follow-up Prioritizer</h1><p>Synthetic CRM. Suggestions are drafts for human review; no message can be sent.</p><button id=load>Load suggested next steps</button><section id=o></section><script>load.onclick=async()=>{let d=await(await fetch('/api/leads')).json();o.innerHTML=d.items.map(x=>`<article><b>${x.lead_id} · ${x.priority}</b><p>${x.reason}</p><p>${x.draft_message}</p></article>`).join('')}</script></body></html>"""
