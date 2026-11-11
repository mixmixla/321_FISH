// Native controls + delayed transport, without replacing production renderers.
const assert=require('node:assert/strict');
module.exports=async function pendingProbe(page,{game,selector,newFrame}){
 await newFrame();
 await page.evaluate(game=>{
  window.cardOriginalAPI=gameAPI;window.cardRPC=[];
  window.cardPendingFrame={public:state.gst.state,private:state.gpriv};
  gameAPI=(op,body)=>new Promise(resolve=>window.cardRPC.push({op,body,resolve}));
  window.cardRepaint=()=>{const root=document.getElementById('cards-proof');root.replaceChildren();GRENDER[game](root,state.gst.state);};
 },game);
 try{
  await page.locator(selector).click();assert.equal(await page.evaluate(()=>cardRPC.length),1);
  await page.evaluate(()=>cardRepaint());assert.equal(await page.locator(selector).isDisabled(),true);
  assert.ok(await page.evaluate(()=>state.gst.state===cardPendingFrame.public&&state.gpriv===cardPendingFrame.private));
  await page.locator(selector).evaluate(button=>button.onclick());assert.equal(await page.evaluate(()=>cardRPC.length),1);
  // Maximizing can also rebuild cosmetic wrappers; the true frames stay equal.
  await page.evaluate(()=>{state.gst={...state.gst,room:{...state.gst.room}};cardRepaint();});
  assert.equal(await page.locator(selector).isDisabled(),true);
  await page.locator(selector).evaluate(button=>button.onclick());assert.equal(await page.evaluate(()=>cardRPC.length),1);
  await page.evaluate(()=>cardRPC[0].resolve({ok:true}));await page.evaluate(()=>cardRepaint());
  assert.equal(await page.locator(selector).isDisabled(),true,'HTTP ack alone must not unlock an old frame');
  await newFrame();assert.equal(await page.locator(selector).isDisabled(),false,'a fresh server frame releases the old latch');
  await page.locator(selector).click();assert.equal(await page.evaluate(()=>cardRPC.length),2);
  await page.evaluate(()=>cardRPC[1].resolve({ok:false,error:'synthetic explicit rejection'}));
  await page.waitForFunction(selector=>!document.querySelector(selector).disabled,selector);
  await page.evaluate(()=>cardRepaint());assert.equal(await page.locator(selector).isDisabled(),false);
  await page.locator(selector).click();assert.equal(await page.evaluate(()=>cardRPC.length),3,'explicit rejection permits a same-frame retry');
  await page.evaluate(()=>cardRPC[2].resolve({ok:true}));assert.equal(await page.locator(selector).isDisabled(),true);
  const requests=await page.evaluate(()=>cardRPC.map(({op,body})=>({op,body})));
  return {sameFrameRedrawBlocked:true,wrapperRedrawBlocked:true,httpAckKeepsLock:true,
   newFrameReleases:true,explicitRejectionRetries:true,mockRequests:requests};
 }finally{
  await page.evaluate(()=>{gameAPI=window.cardOriginalAPI;delete window.cardOriginalAPI;delete window.cardRPC;delete window.cardRepaint;delete window.cardPendingFrame;});
  await newFrame();
 }
};
