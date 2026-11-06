import { CheckCircle2 } from "lucide-react";
import { PanelExpandButton } from './PanelExpandButton.jsx';

export function StudentManifest({ students, counts, onStatusChange, trip, disabled, expanded, onToggleExpand }) {
  function options(student) {
    if (trip?.status === "scheduled") return trip.trip_type === "pickup" ? ["Pending", "Boarded", "Absent"] : ["Boarded", "Absent"];
    if (trip?.status === "in_progress") return student.status === "Pending" ? ["Boarded", "Absent"] : student.status === "Boarded" ? ["Dropped"] : [];
    return [];
  }
  return (
    <section className="panel manifest">
      <header className="panel-header">
        <div>
          <h2>Student manifest</h2>
        </div>
        <PanelExpandButton label="student manifest" expanded={expanded} onToggle={onToggleExpand} />
        <div className="manifest-summary">
          <span className="green">{counts.boarded} Boarded</span>
          <span className="yellow">{counts.pending} Pending</span>
          <span>{counts.dropped} Dropped</span>
          <span>{counts.absent} Absent</span>
        </div>
      </header>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Student name</th>
              <th>Attendance</th>
              <th>Drop-off</th>
              <th>Last seen</th>
            </tr>
          </thead>
          <tbody>
            {students.map((student) => (
              <tr key={student.id} className={student.status.toLowerCase()}>
                <td>
                  <CheckCircle2 size={13} />
                  <strong>{student.name}</strong>
                </td>
                <td>
                  <select
                    className={`status-select ${student.status.toLowerCase()}`}
                    value=""
                    disabled={disabled || options(student).length === 0}
                    onChange={(event) => { if (event.target.value) onStatusChange(student.id, event.target.value); }}
                    aria-label={`Change ${student.name} status`}
                  >
                    <option value="" disabled>{student.status}{!student.reviewed_at ? " *" : ""}</option>
                    {options(student).map((status) => (
                      <option value={status} key={status}>{status}</option>
                    ))}
                  </select>
                </td>
                <td>{student.dropoff}</td>
                <td>{student.lastSeen}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {trip?.status === "scheduled" && <p className="manifest-note">{students.filter(s => !s.reviewed_at).length} awaiting review</p>}
      </div>
      {Boolean(trip?.transfers?.length) && <section className="manifest-note"><h3>Replacement-bus records</h3><ul>{trip.transfers.map((t,i) => <li key={`${t.student_id}-${i}`}><strong>{t.student_name}</strong>: {t.source_bus} → {t.target_bus}. {t.previous_status === 'boarded' ? 'Physical handover confirmed' : 'Reassigned for pickup'} — {t.reason}</li>)}</ul></section>}
    </section>
  );
}
