import { useEffect, useState } from 'react'
import './App.css'

function App() {
  const [message, setMessage] = useState('Loading...')

  useEffect(() => {
    fetch('/api/hello')
      .then((res) => res.json())
      .then((data) => setMessage(data.message))
      .catch(() => setMessage('Backend is not reachable'))
  }, [])

  return (
    <main>
      <h1>Mars Map</h1>
      <p>{message}</p>
    </main>
  )
}

export default App
