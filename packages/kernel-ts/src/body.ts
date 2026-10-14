import {rotateUnitStep} from './kernel.ts';
export type Body = {x:number;y:number;heading_x:number;heading_y:number};
export function advanceBody(body:Body,speed:number,turn:number): Body {
  const [hx,hy]=rotateUnitStep(body.heading_x,body.heading_y,turn*10);
  return {x:body.x+hx*speed*10,y:body.y+hy*speed*10,heading_x:hx,heading_y:hy};
}
export function takeoffVector(body:Body,speed:number):[number,number]{return [body.heading_x*speed,body.heading_y*speed];}
