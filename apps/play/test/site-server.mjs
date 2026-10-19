import {createServer} from 'node:http';
import {readFileSync} from 'node:fs';
import {resolve,extname} from 'node:path';
export const root=resolve(import.meta.dirname,'../../..'),dist=resolve(root,'apps/play/dist');
export const prefix='/internet-vs-one-fly/';
export async function serve(){
 const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.woff2':'font/woff2','.svg':'image/svg+xml','.png':'image/png','.webmanifest':'application/manifest+json'};
 const server=createServer((req,res)=>{try{const url=new URL(req.url,'http://localhost');if(!url.pathname.startsWith(prefix))throw Error('base');const file=resolve(dist,url.pathname.slice(prefix.length)||'index.html');if(!file.startsWith(dist+'/'))throw Error('path');res.setHeader('Content-Type',mime[extname(file)]??'application/octet-stream');res.end(readFileSync(file));}catch{res.writeHead(404,{'Content-Type':'text/html'});res.end(readFileSync(resolve(dist,'404.html')));}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));return {server,origin:`http://127.0.0.1:${server.address().port}`};
}
