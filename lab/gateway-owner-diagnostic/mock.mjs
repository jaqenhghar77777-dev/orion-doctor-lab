import http from 'node:http';
import fs from 'node:fs';
let requests=0;
http.createServer(async(req,res)=>{
 let body='';for await(const b of req)body+=b;
 if(req.method!=='POST'){res.writeHead(404);res.end();return;}
 requests++;
 fs.appendFileSync('/home/replay/model-count.txt',requests+'\n');
 if(requests>1){res.writeHead(429);res.end('one-request limit');return;}
 const input=JSON.parse(body);
 const base={id:'fictional-completion',object:'chat.completion',created:1,model:'fixture'};
 if(input.stream) {
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  for(const delta of [{role:'assistant'},{content:'ORION-FICTIONAL-OK'}])
   res.write('data: '+JSON.stringify({...base,object:'chat.completion.chunk',choices:[{index:0,delta,finish_reason:null}]})+'\n\n');
  res.write('data: '+JSON.stringify({...base,object:'chat.completion.chunk',choices:[{index:0,delta:{},finish_reason:'stop'}],usage:{prompt_tokens:1,completion_tokens:1,total_tokens:2}})+'\n\n');
  res.end('data: [DONE]\n\n');
 } else {
  res.writeHead(200,{'Content-Type':'application/json'});
  res.end(JSON.stringify({...base,choices:[{index:0,message:{role:'assistant',content:'ORION-FICTIONAL-OK'},finish_reason:'stop'}],usage:{prompt_tokens:1,completion_tokens:1,total_tokens:2}}));
 }
}).listen(18081,'127.0.0.1');
