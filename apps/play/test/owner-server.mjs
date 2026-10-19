import {createServer} from '../node_modules/vite/dist/node/index.js';
import {root,prefix} from './site-server.mjs';
export {root,prefix};
export async function serveDev(){
 const server=await createServer({root:root+'/apps/play',configFile:root+'/apps/play/vite.config.ts',server:{host:'127.0.0.1',port:0,strictPort:false,fs:{allow:[root]},watch:{ignored:['**/evidence/**','**/reviews/**','**/.venv/**','**/data/**']}}});
 await server.listen();return {server,origin:`http://127.0.0.1:${server.httpServer.address().port}`};
}
