/* Streamlit component: no network traffic or Python reruns during motion. */
'use strict';
const K = SteeringKinematics, $ = id => document.getElementById(id), canvas = $('canvas'), ctx = canvas.getContext('2d');
const rad = Math.PI/180, deg = 180/Math.PI;
let p, visuals, signature, pose = null, requested = 0, playing = false, direction = 1;
let steeringLimit = 0, geometricLimit = false, appliedAngle = 0;
let motorRange, actuator = null, commandAngle = 0;
let lastTime = 0, frame = 0, warning = '', samples = [], zoom = 1, pan = [0, 0], drag = null;
let width = 1, height = 500, scale = 1, origin = [0, 0], baseScale = 1, baseOrigin = [0, 0];
let reportedHeight = 0;
function degreesLabel(angle, digits = 2) {
  const value=angle*deg;
  return (Math.abs(value)<.5*10**(-digits)?0:value).toFixed(digits)+'°';
}
const colors = {blue:'#3976c4', orange:'#df8628', green:'#138777', ink:'#243548'};
function send(type, extra = {}) { window.parent.postMessage({isStreamlitMessage:true, type, ...extra}, '*'); }
function snapshot() {
  send('streamlit:setComponentValue', {dataType:'json', value:{signature, angle:pose ? pose.theta_left : null,
    steering_angle:appliedAngle, motor_angle:actuator ? actuator.phi-motorRange.neutral_phi : null, applied_angle:commandAngle, requested_angle:requested, sequence:Date.now()}});
}
function resizeHeight() {
  const height = document.body.scrollHeight+8;
  if (height !== reportedHeight) {reportedHeight = height;send('streamlit:setFrameHeight', {height});}
}
function setPlaying(value) {
  playing = value; lastTime = 0;
  $('play').textContent = playing ? 'Ⅱ Pausa' : '▶ Avvia';
  schedule();
}
function motorMode(){return $('control').value==='motor';}
function updateControl(){
  $('angle').min=(motorMode()?Math.min(motorRange.phi_at_lower,motorRange.phi_at_upper):-p.display_range)*deg;
  $('angle').max=(motorMode()?Math.max(motorRange.phi_at_lower,motorRange.phi_at_upper):p.display_range)*deg;
  $('angle-label').textContent=motorMode()?'Angolo motore · ° rispetto alla posa centrale':'Angolo di sterzata · ° (media delle due ruote)';
  $('ratio-label').textContent='Sensibilità sterzo / motore';
  recomputeSamples();
}
function move(angle) {
  requested=angle;warning='';
  if(motorMode()){
    const result=K.resolveMotor(p,angle,motorRange);
    pose=result.pose;actuator=result.actuator;commandAngle=result.angle;
    appliedAngle=actuator ? actuator.steering : 0;
    if(!pose){warning=motorRange.reason||'Il collegamento motore non ammette questa posa.';return false;}
    if(result.limited)warning='Limite del collegamento motore: visualizzata la posa limite calcolata.';
    else if(actuator.sensitivity===null)warning='Prossimità a un punto morto della trasmissione motore–sterzo.';
    return !result.limited;
  }
  const result=K.resolveSteering(p,angle,steeringLimit,geometricLimit);
  pose=result.pose;appliedAngle=pose?(pose.heading_left+pose.heading_right)/2:result.angle;commandAngle=appliedAngle;
  actuator=motorRange.valid&&appliedAngle>=motorRange.mean_lower-1e-12&&appliedAngle<=motorRange.mean_upper+1e-12
    ?K.motorAtSteering(p,appliedAngle,motorRange.neutral_phi):null;
  if(!pose){warning='Limite geometrico: nessuna posa univoca da disegnare.';return false;}
  if(result.limited)warning='Limite geometrico raggiunto: visualizzata la posa limite calcolata.';
  else if(!actuator)warning=motorRange.valid?'Sterzata fuori dalla corsa del collegamento motore: astina non rappresentata.':motorRange.reason;
  else if(pose.nearInput||pose.nearOutput)warning='Allarme: prossimità a un punto morto dello sterzo.';
  return !result.limited;
}
function schedule() { if (!frame) frame = requestAnimationFrame(tick); }
function tick(time) {
  frame = 0;
  if (!p) return;
  if (playing) {
    const dt = lastTime ? Math.min((time-lastTime)/1000, .05) : 0;
    lastTime = time;
    if(dt>0){
      let next=commandAngle+direction*Number($('speed').value)*rad*dt;
      const lower=Number($('angle').min)*rad,upper=Number($('angle').max)*rad;
      if(next>=upper){next=upper;direction=-1;}
      else if(next<=lower){next=lower;direction=1;}
      if(!move(next)){setPlaying(false);snapshot();}
    }
  }
  draw();
  if (playing) schedule();
}
function transform(a) { return [origin[0]+scale*a[0], origin[1]+scale*a[1]]; }
function path(points, stroke, fill = null, dash = [], lineWidth = 1.5) {
  if (!points.length) return;
  ctx.beginPath();
  points.forEach((a,i) => { const [x,y] = transform(a); if (i) ctx.lineTo(x,y); else ctx.moveTo(x,y); });
  if (fill) ctx.closePath();
  ctx.setLineDash(dash); ctx.lineWidth = lineWidth; ctx.strokeStyle = stroke;
  if (fill) {ctx.fillStyle = fill; ctx.fill();}
  ctx.stroke();ctx.setLineDash([]);
}
function text(value, point, color = colors.ink, offset = [0,0], size = 11) {
  const [x,y] = transform(point);ctx.fillStyle=color;ctx.font=`${size}px system-ui`;ctx.textAlign='center';ctx.fillText(value,x+offset[0],y+offset[1]);
}
function circle(a, radius, color, fill = null, dash = []) {
  const [x,y] = transform(a);ctx.beginPath();ctx.arc(x,y,Math.max(.5,radius*scale),0,Math.PI*2);
  ctx.setLineDash(dash);ctx.lineWidth=1.3;ctx.strokeStyle=color;
  if(fill){ctx.fillStyle=fill;ctx.fill();}ctx.stroke();ctx.setLineDash([]);
}
function rectangle(center, w, l, angle) {
  return [[-w/2,-l/2],[w/2,-l/2],[w/2,l/2],[-w/2,l/2]].map(a=>K.add(center,K.rotate(a,angle)));
}
function strip(a,b,w,margin,color,fill) {
  const delta=K.sub(b,a);path(rectangle(K.mul(K.add(a,b),.5),w,K.norm(delta)+margin*2,Math.atan2(delta[1],delta[0])-Math.PI/2),color,fill);
}
function recomputeSamples() {
  samples=[];
  for(let i=0;i<=180;i++) {
    const lower=motorMode()&&motorRange.valid?motorRange.mean_lower:-steeringLimit;
    const upper=motorMode()&&motorRange.valid?motorRange.mean_upper:steeringLimit;
    const angle=lower+(upper-lower)*i/180;
    const s=K.resolveSteering(p,angle,steeringLimit,geometricLimit).pose;
    samples.push(s);
  }
}
function fit() {
  const f=p.physical;
  const reach=Math.max(Math.hypot(p.left.axle_x,p.left.axle_y),Math.hypot(p.right.axle_x,p.right.axle_y),p.left.arm_length,p.right.arm_length)+Math.hypot(f.wheel_width,f.wheel_diameter)/2+22;
  const left=Math.min(-p.pivot_spacing/2-reach,p.motor.x-p.motor.crank_radius-25);
  const right=Math.max(p.pivot_spacing/2+reach,p.motor.x+p.motor.crank_radius+25);
  const half=(right-left)/2, front=Math.max(reach+15,-p.motor.y+p.motor.crank_radius+25),rear=Math.max(reach+15,p.motor.y+p.motor.crank_radius+25);
  baseScale=Math.min((width-45)/(2*half),(height-45)/(front+rear));
  baseOrigin=[width/2-(left+right)*baseScale/2,height/2+(front-rear)*baseScale/2];
}
function draw() {
  const f=p.physical;
  scale=baseScale*zoom;origin=[baseOrigin[0]+pan[0],baseOrigin[1]+pan[1]];
  ctx.clearRect(0,0,width,height);
  // Background and optional trajectories use cached poses, never the Python sweep.
  const xmin=-origin[0]/scale,xmax=(width-origin[0])/scale,ymin=-origin[1]/scale,ymax=(height-origin[1])/scale;
  const grid=25*Math.max(1,Math.ceil(1/zoom));
  for(let x=Math.ceil(xmin/grid)*grid;x<xmax;x+=grid) path([[x,ymin],[x,ymax]],x===0?'#c8d5df':'#e8edf1',null,[],1);
  for(let y=Math.ceil(ymin/grid)*grid;y<ymax;y+=grid) path([[xmin,y],[xmax,y]],y===0?'#c8d5df':'#e8edf1',null,[],1);
  if($('envelope').checked) samples.forEach((s,i)=>{if(s && i%3===0) for(const side of ['left','right']) path(rectangle(s['c_'+side],f.wheel_width,f.wheel_diameter,s['heading_'+side]),'rgba(57,118,196,.13)','rgba(57,118,196,.015)',[],.8);});
  if($('trajectories').checked) for(const attr of ['c_left','c_right','point']) {
    let segment=[];const color=attr==='point'?colors.green:colors.blue;
    for(const s of [...samples,null]) {if(s)segment.push(s[attr]);else{path(segment,color,null,[3,3],1);segment=[];}}
  }
  const al=[-p.pivot_spacing/2,0],ar=[p.pivot_spacing/2,0];
  for(const [a,b] of [[al,p.left],[ar,p.right]]) {
    if($('neutral').checked) {const pts=rectangle(K.add(a,[b.axle_x,b.axle_y]),f.wheel_width,f.wheel_diameter,b.heading_offset);path([...pts,pts[0]],'#94a3b2',null,[5,4],1);}
    if($('construction').checked) circle(a,b.arm_length,'#b4c4cf',null,[3,3]);
  }
  if(pose) {
    if($('construction').checked) circle(pose.b_left,p.tie_length,'#b4c4cf',null,[3,3]);
    for(const side of ['left','right']) {
      strip(pose['a_'+side],pose['c_'+side],visuals.bracket_width,visuals.end_margin,colors.blue,'rgba(57,118,196,.12)');
      strip(pose['a_'+side],pose['b_'+side],visuals.arm_width,visuals.end_margin,colors.blue,'rgba(57,118,196,.24)');
    }
    strip(pose.b_left,pose.b_right,visuals.rod_width,visuals.end_margin,colors.orange,'rgba(223,134,40,.35)');
    for(const [side,name] of [['left','SX'],['right','DX']]) {
      const a=pose['a_'+side],b=pose['b_'+side],c=pose['c_'+side],heading=pose['heading_'+side];
      path(rectangle(c,f.wheel_width,f.wheel_diameter,heading),colors.ink,'#33475c');
      const forward=K.rotate([0,-1],heading),tip=K.add(c,K.mul(forward,f.wheel_diameter*.38));
      path([c,tip],'white',null,[],2);
      path([K.add(tip,K.rotate([-2.5,5],heading)),tip,K.add(tip,K.rotate([2.5,5],heading))],'white',null,[],1.5);
      circle(c,1.4,'white','white');
      for(const joint of [a,b]) {circle(joint,visuals.joint_radius,'#71869b','#ebf2f8');circle(joint,visuals.pin_radius,colors.orange,'white');}
      if($('labels').checked) {text('B '+name,b,colors.orange,[0,19]);text('C '+name,c,colors.ink,[0,f.wheel_diameter*scale/2+15]);text(degreesLabel(heading,1),a,colors.blue,[0,-f.wheel_diameter*scale/2-22],15);}
    }
    circle(pose.point,2.5,colors.green,colors.green);
    if($('labels').checked) text('T',pose.point,colors.green,[0,-10]);
  }
  for(const [a,label] of [[al,'A SX'],[ar,'A DX']]) {circle(a,2.3,'#153f70','#153f70');if($('labels').checked)text(label,a,'#153f70',[0,-12]);}
  if($('labels').checked) {
    const y=Math.max(p.left.arm_length,p.right.arm_length,Math.hypot(p.left.axle_x,p.left.axle_y),Math.hypot(p.right.axle_x,p.right.axle_y))+Math.hypot(f.wheel_width,f.wheel_diameter)/2+15;
    path([[al[0],y],[ar[0],y]],'#8798a8',null,[],1);
    text('Interasse perni · '+p.pivot_spacing+' mm',[0,y],'#667a8d',[0,17]);
  }
  const motorCenter=[p.motor.x,p.motor.y];
  circle(motorCenter,3.5,colors.green,'white');
  if($('construction').checked)circle(motorCenter,p.motor.crank_radius,'#9ecfc4',null,[3,3]);
  if(actuator){
    strip(motorCenter,actuator.pin,visuals.arm_width,visuals.end_margin,colors.green,'rgba(19,135,119,.25)');
    strip(actuator.pin,pose.point,visuals.rod_width,visuals.end_margin,colors.green,'rgba(19,135,119,.12)');
    circle(motorCenter,2,colors.green,'white');circle(actuator.pin,2.2,colors.green,'white');
    if($('labels').checked)text('Q',actuator.pin,colors.green,[0,-12]);
  }
  if($('labels').checked)text('M · motore',motorCenter,colors.green,[0,20]);
  ctx.font='11px system-ui';ctx.textAlign='center';ctx.fillStyle='#718096';ctx.fillText('↑ FRONTE VEICOLO · −Y',width/2,18);
  ctx.textAlign='left';ctx.fillText('X → destra · Y ↓ retro · mm',12,height-12);
  $('angle').value=commandAngle*deg;
  $('reading').textContent=degreesLabel(commandAngle);
  $('mean').textContent=pose?degreesLabel(appliedAngle):'—';
  $('left').textContent=pose ? degreesLabel(pose.heading_left) : '—';
  $('right').textContent=pose ? degreesLabel(pose.heading_right) : '—';
  $('difference').textContent=pose ? degreesLabel(K.wrap(pose.heading_right-pose.heading_left),3) : '—';
  $('ratio').textContent=actuator && actuator.sensitivity!==null ? actuator.sensitivity.toFixed(4) : '—';
  const stoppedMismatch=Math.abs(commandAngle-requested)>1e-10;
  const message=warning+(stoppedMismatch?' Richiesta '+(requested*deg).toFixed(2)+'°; limite mostrato '+(commandAngle*deg).toFixed(2)+'°.':'');
  const status=message || `Vincolo chiuso · ramo ${p.branch>0?'+':''}${p.branch} · T (${pose.point[0].toFixed(2)}, ${pose.point[1].toFixed(2)}) mm`;
  if($('notice').textContent!==status)$('notice').textContent=status;
  $('notice').classList.toggle('warning',!!warning);
}
$('play').onclick=()=>{if(playing){setPlaying(false);snapshot();}else setPlaying(true);};
$('zero').onclick=()=>{setPlaying(false);direction=1;move(0);snapshot();schedule();};
$('angle').oninput=()=>{setPlaying(false);move(Number($('angle').value)*rad);schedule();};
$('angle').onchange=snapshot;
$('control').onchange=()=>{setPlaying(false);direction=1;updateControl();move(0);snapshot();schedule();};
$('fit').onclick=()=>{zoom=1;pan=[0,0];schedule();};
for(const id of ['labels','construction','trajectories','neutral','envelope']) $(id).onchange=schedule;
canvas.onwheel=e=>{e.preventDefault();zoom=Math.max(.3,Math.min(8,zoom*Math.exp(-e.deltaY*.001)));schedule();};
canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY,...pan];canvas.setPointerCapture(e.pointerId);};
canvas.onpointermove=e=>{if(drag){pan=[drag[2]+e.clientX-drag[0],drag[3]+e.clientY-drag[1]];schedule();}};
canvas.onpointerup=()=>{drag=null;};canvas.onpointercancel=()=>{drag=null;};
document.addEventListener('visibilitychange',()=>{if(document.hidden && playing){setPlaying(false);snapshot();}});
new ResizeObserver(resizeHeight).observe(document.body);
new ResizeObserver(()=>{
  const bounds=canvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1;
  width=Math.max(1,bounds.width);height=bounds.height;
  canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);
  if(p){fit();schedule();}resizeHeight();
}).observe(canvas);
window.addEventListener('message',event=>{
  if(event.source!==window.parent || event.data.type!=='streamlit:render')return;
  const args=event.data.args;
  if(signature===args.signature)return; // preserve animation through unrelated server reruns
  signature=args.signature;p=args.parameters;visuals=args.display_dimensions;
  steeringLimit=args.steering_limit;geometricLimit=args.geometric_limit;motorRange=args.motor_range;
  $('control').options[0].disabled=!motorRange.valid;
  if(!motorRange.valid)$('control').value='steering';
  setPlaying(false);pose=null;requested=0;direction=1;zoom=1;pan=[0,0];
  updateControl();
  move(0);fit();schedule();resizeHeight();
});
send('streamlit:componentReady',{apiVersion:1});resizeHeight();
