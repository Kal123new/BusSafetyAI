// An isolated fictional workspace. Never uses the production database or tokens.
const key = 'safesense-public-sample-v1';
export const inSample = () => sessionStorage.getItem('safesense-sample') === 'true';
export function selectSample(enabled) { sessionStorage.setItem('safesense-sample', String(enabled)); }
const now = () => Date.now()/1000;
function freshTrip() {
  return { id: 'sample-trip', trip_code: 'SAMPLE-001', bus_id: 'sample-bus', bus_code: 'DEMO', driver_id: 'sample-driver', status: 'scheduled', version: 1, shift: 'morning', trip_type: 'pickup', service_date: new Date().toISOString().slice(0,10), route_approved: false, motion: { status: 'unknown' }, transfers: [],
    students: ['Alex Example','Sam Sample'].map((name,index)=>({student_id:`sample-${index}`,first_name:name.split(' ')[0],last_name:name.split(' ')[1],status:'pending',reviewed_at:null,boarded_at:null,dropped_at:null,pickup_stop_id:'sample-home',dropoff_stop_id:'sample-school'})),
    stops: [{id:'sample-home',stop_id:'sample-home',name:'Example pickup stop',sequence:0,latitude:25.2048,longitude:55.2708},{id:'sample-school',stop_id:'sample-school',name:'Example school',sequence:1,latitude:25.2108,longitude:55.2808}] };
}
export function resetSample() { localStorage.removeItem(key); }
function snapshot(trip) {
  trip.counts={manifest_total:trip.students.length,on_bus_count:trip.students.filter(s=>s.status==='boarded').length,pending_count:trip.students.filter(s=>s.status==='pending').length,dropped_count:trip.students.filter(s=>s.status==='dropped').length,absent_count:trip.students.filter(s=>s.status==='absent').length};
  return trip;
}
function fail(message, status=422) { const error=new Error(message);error.status=status;throw error; }
export async function sampleApi(path, options={}) {
  const store=JSON.parse(localStorage.getItem(key)||'null') || { trip:freshTrip(), receipts:{} };
  const trip=snapshot(store.trip);
  const body=options.body ? JSON.parse(options.body) : {};
  if(path==='/api/v1/me') return {id:'local-sample',role:'driver',driver_id:'sample-driver'};
  if(path==='/api/v1/trips/ensure-daily') return {created:0};
  if(path==='/api/v1/trips') return [trip];
  if(path==='/api/v1/capabilities') return {routing_configured:false,tile_url:'https://tile.openstreetmap.org/{z}/{x}/{y}.png',tile_attribution:'© OpenStreetMap contributors',public_live_locations:true,public_demo_services:false};
  if(path==='/api/v1/trips/sample-trip/route') return {route:null};
  if(path==='/api/v1/trips/sample-trip') return trip;
  if(path.endsWith('/locations')) return {sample_interval_s:10,arrival_status:'unknown'};
  const action=path.replace('/api/v1/trips/sample-trip/','');
  const receipt=options.headers?.['Idempotency-Key'];
  if(!receipt) fail('This operation is not available in the public sample. Sign in for shared operations.');
  const signature=JSON.stringify({path,body});
  if(store.receipts[receipt]) { if(store.receipts[receipt].signature!==signature) fail('Request key already used',409); return store.receipts[receipt].result; }
  if(body.expected_version!==trip.version) fail('Sample changed in another tab; refresh and try again',409);
  if(!body.operator_confirmed_stopped) fail('Confirm the bus is stopped.');
  if(action==='start') {
    if(trip.status!=='scheduled'||!trip.students.every(s=>s.reviewed_at)||!body.route_confirmed) fail('Review every student and confirm the route before starting.');
    trip.status=trip.students.every(s=>s.status==='absent')?'awaiting_safety_check':'in_progress'; trip.started_at=now();trip.route_approved=true;
  } else if(action.startsWith('students/')) {
    if(!['scheduled','in_progress'].includes(trip.status)) fail('Attendance cannot change after the trip has ended.');
    const student=trip.students.find(s=>s.student_id===action.split('/')[1]); if(!student)fail('Student not found',404);
    if(!['pending','boarded','dropped','absent'].includes(body.status))fail('Invalid attendance status');
    if(trip.status==='scheduled'&&body.status==='dropped')fail('Start the trip before recording drop-off.');
    if(body.status==='dropped'&&student.status!=='boarded')fail('Only a boarded student can be dropped off.');
    if(trip.status==='in_progress'&&(body.override_reason||'').trim().length<10)fail('Enter a manual stop confirmation reason.');
    student.status=body.status;student.reviewed_at=now();
    if(body.status==='boarded')student.boarded_at=now();
    if(body.status==='dropped')student.dropped_at=now();
    if(trip.status==='in_progress'&&trip.students.every(s=>['dropped','absent'].includes(s.status))) {trip.status='awaiting_safety_check';trip.last_dropoff_at=now();trip.stops.forEach(s=>s.completed_at=now());}
  } else if(action==='finish') {
    if(trip.status!=='awaiting_safety_check'||!body.physically_inspected||!body.physically_empty||(body.notes||'').trim().length<5)fail('Complete the physical inspection and notes.');
    trip.status='finished';trip.ended_at=now();
  } else fail('Sign in to use shared trip management.');
  trip.version++;snapshot(trip);store.receipts[receipt]={signature,result:structuredClone(trip)};
  localStorage.setItem(key,JSON.stringify(store));return trip;
}
