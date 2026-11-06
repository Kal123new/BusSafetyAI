export const initialStudents = [
  { id: 1, name: "Rivera, Marcus", status: "Boarded", dropoff: "-", seat: "A2", lastSeen: "7:41 AM" },
  { id: 2, name: "Thornton, Alyssa", status: "Boarded", dropoff: "-", seat: "B1", lastSeen: "7:39 AM" },
  { id: 3, name: "Nakamura, Ethan", status: "Boarded", dropoff: "-", seat: "A4", lastSeen: "7:38 AM" },
  { id: 4, name: "Patterson, Chloe", status: "Boarded", dropoff: "-", seat: "C2", lastSeen: "7:36 AM" },
  { id: 5, name: "Guzman, Sofia", status: "Boarded", dropoff: "-", seat: "B3", lastSeen: "7:34 AM" },
  { id: 6, name: "Washington, Dilan", status: "Boarded", dropoff: "-", seat: "C1", lastSeen: "7:33 AM" },
  { id: 7, name: "Kowalski, Emma", status: "Boarded", dropoff: "-", seat: "A1", lastSeen: "7:31 AM" },
  { id: 8, name: "Delgado, Noah", status: "Pending", dropoff: "-", seat: "-", lastSeen: "-" },
  { id: 9, name: "Okafor, Amara", status: "Pending", dropoff: "-", seat: "-", lastSeen: "-" },
  { id: 10, name: "Brennan, Liam", status: "Pending", dropoff: "-", seat: "-", lastSeen: "-" },
  { id: 11, name: "Singh, Priya", status: "Pending", dropoff: "-", seat: "-", lastSeen: "-" },
  { id: 12, name: "Chan, Mei-Lin", status: "Dropped", dropoff: "Dropped", seat: "A3", lastSeen: "7:28 AM" },
  { id: 13, name: "Flores, Daniel", status: "Dropped", dropoff: "Dropped", seat: "B2", lastSeen: "7:25 AM" }
];

export const routeStops = [
  { name: "Depot", distanceToNext: "1.2 mi", etaToNext: "5 min" },
  { name: "Pine Ave", distanceToNext: "0.9 mi", etaToNext: "4 min" },
  { name: "Cedar Lane", distanceToNext: "0.7 mi", etaToNext: "3 min" },
  { name: "Maple Grove Dr & 5th Ave", distanceToNext: "0.4 mi", etaToNext: "2 min" },
  { name: "Oakridge Ln", distanceToNext: "0.6 mi", etaToNext: "3 min" },
  { name: "Westfield Elementary", distanceToNext: "0 mi", etaToNext: "Arrived" }
];

export const initialActivity = [
  { id: 1, time: "7:41", text: "Rivera, Marcus boarded at Stop 6", tone: "good" },
  { id: 2, time: "7:39", text: "Thornton, Alyssa boarded at Stop 6", tone: "good" },
  { id: 3, time: "7:38", text: "Nakamura, Ethan boarded at Stop 5", tone: "good" },
  { id: 4, time: "7:28", text: "Chan, Mei-Lin dropped off at Stop 2", tone: "muted" },
  { id: 5, time: "7:25", text: "Flores, Daniel dropped off at Stop 2", tone: "muted" }
];
