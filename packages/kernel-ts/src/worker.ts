import {runCase} from './runner.ts';
self.onmessage=async(event)=>{
  const {id,buffer,log,digests=true}=event.data;
  try {self.postMessage({id,result:await runCase(buffer,log,digests)});}
  catch(error){self.postMessage({id,error:String(error)});}
};
