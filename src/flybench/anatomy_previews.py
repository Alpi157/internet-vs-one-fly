"""Static measured-anatomy previews; all displayed scale bars are physical."""
import gzip
import json
import numpy as np
from .anatomy import decode_arbors, project
from .anatomy_layout import LABEL


def lamina_preview(volume, destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(9,6),facecolor='black')
    resolution=np.array(volume['scale']['resolution'])/1000
    for ax,name in zip(axes,('LA(L)','LA(R)')):
        label=next(k for k,n in volume['names'].items() if n==name)
        mask=np.any(volume['volume']==label,axis=2);coords=np.argwhere(mask)
        low=coords.min(axis=0)*resolution[:2]-20;high=(coords.max(axis=0)+1)*resolution[:2]+20
        from matplotlib.colors import ListedColormap
        ax.imshow(mask.T,extent=[0,mask.shape[0]*resolution[0],mask.shape[1]*resolution[1],0],interpolation='nearest',cmap=ListedColormap(['black','#cc28ad']))
        for axis in range(2):
            step=volume['scale']['chunk_sizes'][0][axis]*resolution[axis]
            for plane in np.arange(0,high[axis]+step,step):
                (ax.axvline if axis==0 else ax.axhline)(plane,color='gray',lw=.5)
        ax.set_xlim(low[0],high[0]);ax.set_ylim(high[1],low[1]);ax.set_aspect('equal');ax.tick_params(colors='white')
        x,y=low[0]+10,high[1]-10;ax.plot([x,x+100],[y,y],c='white',lw=2);ax.text(x,y-6,'100 µm',color='white',fontsize=8)
        ax.set_title(name+' frontal occupancy raster',color='white');ax.set_xlabel('Source x (µm)',color='white');ax.set_ylabel('Source y (µm)',color='white')
    fig.suptitle(LABEL+'\nGray lines: documented source chunk planes',color='white',fontsize=8)
    fig.tight_layout(rect=[0,0,1,.92]);fig.savefig(destination/'lamina-inspection.png',dpi=140);plt.close(fig)


def previews(manifest, roi, circuits, directory, destination, skeletons=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    destination.mkdir(parents=True, exist_ok=True)
    colors={'LC4':'#0072b2','LPLC2':'#e69f00','giant fiber':'#cc79a7','walking DNs':'#009e73','interior':'#596474'}
    decoded={}
    for a in manifest['assets']:
        if a['lod']=='desktop': decoded[a['circuit']]=decode_arbors(gzip.decompress((directory/a['file']).read_bytes()))

    def draw_tree(ax, points, parents, bridges, color, width, alpha):
        edge=np.flatnonzero(parents>=0);normal=edge[~bridges[edge]];cross=edge[bridges[edge]]
        if len(normal):ax.add_collection(LineCollection(np.stack([points[normal],points[parents[normal]]],axis=1),colors=color,linewidths=width,alpha=alpha))
        if len(cross):ax.add_collection(LineCollection(np.stack([points[cross],points[parents[cross]]],axis=1),colors='#efaf39',linewidths=.65,linestyles='dashed',alpha=.8))

    def decorate(ax, low, high):
        ax.set_facecolor('black');ax.set_xlim(low[0],high[0]);ax.set_ylim(high[1],low[1]);ax.set_aspect('equal')
        ax.tick_params(colors='white');ax.set_xlabel('Shared horizontal (µm)',color='white');ax.set_ylabel('Panel vertical coordinate (µm)',color='white')
        sx,sy=low[0]+10,high[1]-15
        ax.plot([sx,sx+100],[sy,sy],color='white',lw=2);ax.text(sx,sy-6,'100 µm',color='white',fontsize=8)

    index=[]
    for name,circuit in [('neuropils',None),('T1b-arbors','T1b'),('giant-fiber','T1b'),('T1a-arbors','T1a'),('T1b-brain-1to1','T1b')]:
        brain_only=name=='T1b-brain-1to1'
        low=np.array(manifest['bounding_box_um'][:2])-10;high=np.array(manifest['bounding_box_um'][2:])+10
        if brain_only:
            d=decoded[circuit];p=d['points'][d['panels']==0]
            low=np.floor(p.min(axis=0)-10);high=np.ceil(p.max(axis=0)+10)
            width,height=(high-low).astype(int);margin=100;W,H=width+margin*2,height+margin*2
            fig=plt.figure(figsize=(W/100,H/100),dpi=100,facecolor='black')
            ax=fig.add_axes([margin/W,margin/H,width/W,height/H]);dpi=100
        else:
            fig,ax=plt.subplots(figsize=(8,11),facecolor='black');dpi=140
        paths=[p for r in roi['rois'] if not brain_only or r['panel']==0 for p in r['contours_um']]
        ax.add_collection(LineCollection(paths,colors='#cc28ad',linewidths=.4,alpha=.65))
        if circuit:
            d=decoded[circuit];brain=circuits[circuit][1]
            for group in ['interior','LC4','LPLC2','walking DNs','giant fiber']:
                if brain_only and group=='walking DNs':continue
                for i,node in enumerate(brain['nodes']):
                    if node['group']!=group or (name=='giant-fiber' and group!='giant fiber'):continue
                    row=d['neurons'][i];first=int(row['first']);end=first+int(row['count'])
                    points=d['points'][first:end];parents=d['parents'][first:end].copy();parents[parents>=0]-=first
                    if brain_only:
                        permitted=d['panels'][first:end]==0
                        parents[~permitted]=-1
                        child=np.flatnonzero(parents>=0);parents[child[~permitted[parents[child]]]]=-1
                    draw_tree(ax,points,parents,d['bridges'][first:end],colors[group],.25 if group=='interior' else .8,.05 if group=='interior' else .85)
                ax.plot([],[],color=colors[group],label=group)
            ax.legend(loc='upper right',facecolor='black',labelcolor='white',fontsize=7)
        if name=='giant-fiber':
            selected=[d['points'][int(d['neurons'][i]['first']):int(d['neurons'][i]['first'])+int(d['neurons'][i]['count'])] for i,n in enumerate(brain['nodes']) if n['group']=='giant fiber']
            p=np.concatenate(selected);low=p.min(axis=0)-15;high=p.max(axis=0)+15
        decorate(ax,low,high)
        if name=='giant-fiber':
            frame=json.loads((directory/'frame.json').read_text())
            for check in frame['evidence']['giant_fiber_sanity']['neurons']:
                soma=check['annotated_soma_display_um'];branch=check['branch_display_um']
                ax.scatter(*soma,s=14,facecolors='none',edgecolors='white');ax.scatter(*branch,s=10,c='#efaf39')
        title=name+(' · 1 pixel = 1 µm' if brain_only else '')
        fig.suptitle(title+'\n'+LABEL+'\nAmber dashed bridges: layout, not anatomy',color='white',fontsize=8)
        if not brain_only:fig.tight_layout(rect=[0,0,1,.94])
        fig.savefig(destination/(name+'.png'),dpi=dpi);plt.close(fig)
        index.append(dict(file=name+'.png',view=LABEL,scale_bar_um=100,pixels_per_um=1 if brain_only else None,aspect='equal physical units',bounds_um=[*low.tolist(),*high.tolist()]))
    if skeletons is not None:
        selections=[];brain=circuits['T1b'][1]
        for group in ('giant fiber','LC4','LPLC2'):
            node=min((n for n in brain['nodes'] if n['group']==group),key=lambda n:int(n['body_id']))
            body=int(node['body_id']);xyz,parent,_=skeletons[body];raw=project(xyz,manifest['frame'])
            low=raw.min(axis=0)-15;high=raw.max(axis=0)+15
            if high[0]-low[0]<140:
                mid=(low[0]+high[0])/2;low[0]=mid-70;high[0]=mid+70
            height=min(13,max(3,4*(high[1]-low[1])/(high[0]-low[0])+1))
            fig,axes=plt.subplots(1,3,figsize=(12,height),facecolor='black')
            for ax,lod in zip(axes,('raw','desktop','phone')):
                if lod=='raw':
                    points,links=raw,parent;pp=(xyz[:,manifest['frame']['split']['axis']]>=manifest['frame']['split']['boundary_um']);bridges=np.zeros(len(pp),bool)
                    children=np.flatnonzero(parent>=0);bridges[children]=pp[children]!=pp[parent[children]];subtitle='raw SWC'
                else:
                    asset=next(a for a in manifest['assets'] if a['circuit']=='T1b' and a['lod']==lod)
                    d=decode_arbors(gzip.decompress((directory/asset['file']).read_bytes()));i=next(i for i,n in enumerate(brain['nodes']) if n['body_id']==str(body))
                    row=d['neurons'][i];first=int(row['first']);end=first+int(row['count'])
                    points=d['points'][first:end];links=d['parents'][first:end].copy();links[links>=0]-=first;bridges=d['bridges'][first:end]
                    subtitle=f"{lod}: twig < {asset['highlighted_twig_um']} µm; DP {asset['tolerance_um']} µm"
                draw_tree(ax,points,links,bridges,'#cc79a7',.45,.9);decorate(ax,low,high);ax.set_title(subtitle,color='white',fontsize=9)
            fig.suptitle(f'{group}, body {body}: raw versus display simplification\n'+LABEL+'\nAmber dashed bridges: layout, not anatomy',color='white',fontsize=8)
            fig.tight_layout(rect=[0,0,1,.94]);name=group.replace(' ','-')+'-raw-versus-pruned.png'
            fig.savefig(destination/name,dpi=140);plt.close(fig)
            selections.append(dict(group=group,body_id=str(body),rule='Lowest body ID in this T1b brain.json group',file=name))
            index.append(dict(file=name,view=LABEL,scale_bar_um=100))
        (destination/'pruning-previews.json').write_text(json.dumps(dict(frame=manifest['frame'],selection=selections),indent=2,sort_keys=True)+'\n')
    (destination/'previews.json').write_text(json.dumps(index,indent=2,sort_keys=True)+'\n')
