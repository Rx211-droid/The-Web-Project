import React, { useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

gsap.registerPlugin(ScrollTrigger)

const PROJECTS = new Array(6).fill(0).map((_, i) => ({ 
  id: i + 1, 
  title: `Project ${i + 1}`, 
  description: 'Short description of the project and its treatment.', 
  date: '2024' 
}))

export default function Projects() { 
  const ref = useRef(null)

  useEffect(() => { 
    // GSAP Scroll animation for project cards
    const q = gsap.utils.selector(ref)
    gsap.from(q('.card'), { 
      y: 40, 
      autoAlpha: 0, 
      duration: 0.9, 
      stagger: 0.12, 
      ease: 'power3.out', 
      scrollTrigger: { 
        trigger: ref.current, 
        start: 'top 80%', 
      } 
    }) 
  }, [])

  return (
    <main id="projects" className="py-20 px-6 md:px-12 lg:px-24 bg-gradient-to-b from-white to-gray-50" ref={ref}>
      <div className="max-w-6xl mx-auto">
        <h2 className="text-3xl md:text-4xl font-bold mb-8">Selected Projects</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {PROJECTS.map((p) => (
            <motion.article 
              key={p.id} 
              className="card rounded-2xl overflow-hidden shadow-sm bg-white hover:shadow-lg transition-transform" 
              whileHover={{ scale: 1.02 }}
            >
              <div className="aspect-video bg-gray-100 flex items-center justify-center"> 
                <span className="text-sm text-gray-500">Placeholder visual</span>
              </div>
              <div className="p-6">
                <h3 className="font-semibold text-lg">{p.title}</h3>
                <p className="text-sm mt-2 text-gray-600">{p.description}</p>
                <div className="mt-4 flex items-center justify-between">
                  <a href="#" className="text-sm underline">View project</a>
                  <span className="text-xs text-gray-400">{p.date}</span>
                </div>
              </div>
            </motion.article>
          ))}
        </div>
      </div>
    </main>
  ) 
}
