import {defineConfig} from 'vite';
export default defineConfig({
    base:'/internet-vs-one-fly/',
    plugins:[{
        name:'raw-gzip-data-in-dev',
        apply:'serve',
        configureServer(server){
            // These are data containers explicitly decompressed by the existing
            // graph/anatomy readers. Vite's static server otherwise marks .gz
            // as HTTP compression, so browsers decompress them a second time.
            // Preserve the container bytes; the frozen readers stay untouched.
            server.middlewares.use((request,response,next)=>{
                if((request.url??'').split('?')[0].endsWith('.gz')){
                    const setHeader=response.setHeader.bind(response);
                    response.setHeader=(name,value)=>name.toLowerCase()==='content-encoding'?response:setHeader(name,value);
                }
                next();
            });
        }
    }]
});
