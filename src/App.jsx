import React from 'react'
import Hero from './components/Hero'
import Projects from './components/Projects'

export default function App() {
  return (
    <div className="min-h-screen bg-white text-gray-900">
      <Hero />
      <Projects />
      <footer className="py-12 text-center text-sm text-gray-500">© Your Studio — Replace with your info</footer>
    </div>
  )
}
