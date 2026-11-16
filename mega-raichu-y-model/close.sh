#!/bin/sh
# close-up probe of the body: copies the config with a tight camera into scratch/, previews it
cd /Users/manta/SpriteDrawer && mkdir -p mega-raichu-y-model/scratch
/usr/local/bin/python3 -c "
import json;c=json.load(open('mega-raichu-y-model/mega_raichu_y_front.json'))
c['model']='../'+c['model'];c['camera']['target']=[0,0,0.35];c['camera']['ortho_scale']=1.3
json.dump(c,open('mega-raichu-y-model/scratch/close.json','w'))"
/usr/local/bin/python3 pipeline/preview.py mega-raichu-y-model/scratch/close.json mega-raichu-y-model/scratch/close.png --frames ${1:-1} --views ${2:-sprite,side} --size 360 2>&1 | tail -1
