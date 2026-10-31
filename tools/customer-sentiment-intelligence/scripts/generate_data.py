from pathlib import Path
import random
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/generated/reviews.csv'
templates={
 'positive': ["The {item} works wonderfully and the quality feels excellent.","I love this {item}; setup was easy and support was helpful.","Fast delivery and a great {item}. I am very satisfied."],
 'negative': ["The {item} broke quickly and the quality is disappointing.","I am frustrated with this {item}; setup failed and support was unhelpful.","Late delivery and a poor {item}. I would not recommend it."],
 'neutral': ["The {item} arrived on Tuesday and matches the listed size.","I received the {item}; it has the features described on the page.","The {item} is average. I have used it for one week."],
}
items=['desk lamp','travel mug','notebook','headphones','storage box','keyboard']
rows=[]
for month in range(1,13):
 for i in range(90):
  label=random.choices(list(templates),[.42,.36,.22])[0]
  rows.append({'review_id':f'SYN-{month:02}-{i:03}','review_date':f'2025-{month:02}-15','text':random.choice(templates[label]).format(item=random.choice(items)),'sentiment':label})
OUT.parent.mkdir(parents=True,exist_ok=True)
pd.DataFrame(rows).to_csv(OUT,index=False)
print(f'Wrote {len(rows)} synthetic reviews to {OUT}')
