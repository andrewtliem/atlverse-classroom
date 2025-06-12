import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'

function StudentDashboard() {
  return <h2>Student Dashboard (mobile)</h2>
}

function TeacherDashboard() {
  return <h2>Teacher Dashboard (mobile)</h2>
}

function Home() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '2rem' }}>
      <Link to="/student" style={{ fontSize: '1.2rem' }}>Student View</Link>
      <Link to="/teacher" style={{ fontSize: '1.2rem' }}>Teacher View</Link>
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/student" element={<StudentDashboard />} />
        <Route path="/teacher" element={<TeacherDashboard />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
