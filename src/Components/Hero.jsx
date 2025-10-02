import React, { useRef, useEffect, useState } from 'react'
import { motion, useCycle } from 'framer-motion'
import { Howl } from 'howler'
import * as THREE from 'three'

export default function Hero() {
  const [playing, setPlaying] = useState(false)
  const audioRef = useRef(null)
  const canvasRef = useRef(null)

  useEffect(() => {
    // Simple Three.js placeholder scene — replace with your own 3D or shader
    const canvas = canvasRef.current
    if (!canvas) return
    
    // Scene Setup
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(50, canvas.clientWidth / canvas.clientHeight, 0.1, 1000)
    camera.position.z = 5
    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true })
    renderer.setSize(canvas.clientWidth, canvas.clientHeight)

    // 3D Object (Torus Knot)
    const geometry = new THREE.TorusKnotGeometry(1.6, 0.4, 128, 32)
    const material = new THREE.MeshNormalMaterial({ flatShading: true })
    const mesh = new THREE.Mesh(geometry, material)
    scene.add(mesh)

    // Animation Loop
    let mounted = true
    function animate() {
      if (!mounted) return
      mesh.rotation.x += 0.006
      mesh.rotation.y += 0.01
      renderer.render(scene, camera)
      requestAnimationFrame(animate)
    }
    animate()

    // Handle Resize
    const onResize = () => {
      renderer.setSize(canvas.clientWidth, canvas.clientHeight)
      camera.aspect = canvas.clientWidth / canvas.clientHeight
      camera.updateProjectionMatrix()
    }
    window.addEventListener('resize', onResize)

    return () => {
      mounted = false
      window.removeEventListener('resize', onResize)
      // Cleanup for Three.js
      renderer.dispose && renderer.forceContextLoss && renderer.forceContextLoss() 
    }

  }, [])

  useEffect(() => { 
    // Preload audio (use your own asset)
    audioRef.current = new Howl({ 
      src: ['/assets/ambient-loop.mp3'], // NOTE: You need to add this file
      loop: true, 
      volume: 0.6, 
    }) 
  }, [])

  const toggleAudio = () => {
    if (!audioRef.current) return
    if (playing) audioRef.current.pause() 
    else audioRef.current.play()
    setPlaying((p) => !p)
  }

  return (
    <header className="relative h-screen flex items-center justify-center overflow-hidden">
      <canvas ref={canvasRef} className="absolute inset-0 w-full h-full pointer-events-none" />

      {/* Repeating big letters in background (css-based) */}
      <div className="absolute inset-0 flex flex-wrap items-center justify-center opacity-10 select-none pointer-events-none">
        {Array.from({ length: 20 }).map((_, i) => (
          <motion.span
            key={i}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1, rotate: (i % 7) * 8 }}
            transition={{ delay: i * 0.03 }}
            className="text-7xl md:text-9xl font-extrabold m-3"
            style={{ transformOrigin: 'center' }}
          >
            U
          </motion.span>
        ))}
      </div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.9 }}
        className="relative z-10 text-center max-w-4xl px-6"
      >
        <div className="uppercase text-sm text-teal-600 mb-4 font-semibold">Unseen Studio® • clone</div>
        <h1 className="text-4xl md:text-6xl lg:text-7xl font-extrabold leading-tight">
          A brand, digital & motion studio creating
          <br /> <span className="bg-clip-text text-transparent bg-gradient-to-r from-teal-500 to-indigo-600">refreshingly unexpected ideas</span>
        </h1>

        <p className="mt-6 text-lg text-gray-600">Interactive motion, audio and 3D backgrounds — a heavy animation experience.</p>

        <div className="mt-10 flex items-center justify-center gap-4">
          <motion.a whileTap={{ scale: 0.96 }} href="#projects" className="px-6 py-3 rounded-md border border-gray-900/10 shadow-sm">
            Enter
          </motion.a>

          <motion.button
            whileTap={{ scale: 0.96 }}
            onClick={toggleAudio}
            className="px-6 py-3 rounded-md bg-gray-900 text-white"
            aria-pressed={playing}
          >
            {playing ? 'Pause audio' : 'Play audio'}
          </motion.button>
        </div>
      </motion.div>
    </header>
  )
}
