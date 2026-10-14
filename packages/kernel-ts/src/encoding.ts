import { atanApprox } from './kernel.ts';
export type Strike = { active:boolean; aim_x:number; aim_y:number; elapsed_ms:number; downward_speed_per_ms:number; hand_radius?:number };
export function encodeHand(strike: Strike, x:number,y:number,hx:number,hy:number,gain:number): Record<string,number> {
  const r=strike.hand_radius ?? .75,H=8,dt=.5;
  if(!Number.isFinite(r)||r<=0||r>64)throw new Error("hand radius domain");
  const zero={angular_radius:0,angular_expansion_per_ms:0,size_feature:0,expansion_feature:0,left_fraction:.5,right_fraction:.5,lc4_left_drive:0,lc4_right_drive:0,lplc2_left_drive:0,lplc2_right_drive:0};
  if (![x,y,hx,hy,gain,strike.aim_x,strike.aim_y,strike.elapsed_ms,strike.downward_speed_per_ms].every(Number.isFinite) || gain<0 || strike.elapsed_ms<0 || strike.downward_speed_per_ms<0) throw new Error('encoder domain');
  if (!strike.active || strike.downward_speed_per_ms*strike.elapsed_ms>=H) return zero;
  let height=H-strike.downward_speed_per_ms*strike.elapsed_ms;
  if (height<0) height=0;
  const previousHeight=height+strike.downward_speed_per_ms*dt;
  const dx=strike.aim_x-x,dy=strike.aim_y-y;
  const planar=Math.sqrt(dx*dx+dy*dy);
  const distance=Math.sqrt(planar*planar+height*height);
  const previousDistance=Math.sqrt(planar*planar+previousHeight*previousHeight);
  const bounded=distance>r/8 ? distance:r/8;
  const boundedPrevious=previousDistance>r/8 ? previousDistance:r/8;
  const angular=atanApprox(r/bounded);
  const previous=atanApprox(r/boundedPrevious);
  let expansion=(angular-previous)/dt;
  if (expansion<0) expansion=0;
  let cross=0;
  if (planar>0) { cross=hx*(dy/planar)-hy*(dx/planar); if(cross < -1)cross=-1;else if(cross>1)cross=1; }
  const left=.5*(1+cross),right=1-left;
  const size=Math.min(1,Math.max(0,angular/atanApprox(8)));
  const peak=r*.05/((r/8)*(r/8)+r*r);
  const expanding=Math.min(1,Math.max(0,expansion/peak));
  const sizeDrive=expansion>0 ? gain*size:0;
  const expansionDrive=gain*expanding;
  return {angular_radius:angular,angular_expansion_per_ms:expansion,size_feature:size,expansion_feature:expanding,left_fraction:left,right_fraction:right,
    lc4_left_drive:expansionDrive*left,lc4_right_drive:expansionDrive*right,lplc2_left_drive:sizeDrive*left,lplc2_right_drive:sizeDrive*right};
}
