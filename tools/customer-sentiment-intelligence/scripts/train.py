import json
from pathlib import Path
import joblib
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.pipeline import Pipeline

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/generated/reviews.csv'
OUT=ROOT/'artifacts'
THEMES={'quality':['quality','broke','excellent','poor'], 'delivery':['delivery','late','arrived'], 'support':['support','helpful','unhelpful'], 'setup':['setup','easy','failed']}

def run():
 if not DATA.exists(): raise SystemExit('Generate data first: python scripts/generate_data.py')
 df=pd.read_csv(DATA,parse_dates=['review_date'])
 cutoff=df.review_date.quantile(.8)
 train=df[df.review_date<cutoff]; test=df[df.review_date>=cutoff]
 model=Pipeline([('tfidf',TfidfVectorizer(ngram_range=(1,2),min_df=2)),('classifier',LogisticRegression(max_iter=1000,class_weight='balanced',random_state=13))])
 model.fit(train.text,train.sentiment)
 pred=model.predict(test.text)
 dummy=DummyClassifier(strategy='most_frequent').fit(train.text,train.sentiment)
 report={'dataset':'synthetic authored review templates','train_end':str(train.review_date.max().date()),'test_start':str(test.review_date.min().date()),'train_rows':len(train),'test_rows':len(test),'baseline':{'accuracy':accuracy_score(test.sentiment,dummy.predict(test.text)),'macro_f1':f1_score(test.sentiment,dummy.predict(test.text),average='macro')},'tfidf_logistic':{'accuracy':accuracy_score(test.sentiment,pred),'macro_f1':f1_score(test.sentiment,pred,average='macro'),'per_class':classification_report(test.sentiment,pred,output_dict=True,zero_division=0)},'limitations':['Synthetic templated text has narrow vocabulary and an easy temporal split.','Keyword themes are heuristic tags, not topic discovery.','No causal relationship or real customer voice is represented.']}
 OUT.mkdir(exist_ok=True); joblib.dump({'model':model,'themes':THEMES},OUT/'sentiment.joblib'); (OUT/'evaluation.json').write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2))
if __name__=='__main__':run()
