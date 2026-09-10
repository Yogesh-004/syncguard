"use client"
import { useRef } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useGSAP } from '@gsap/react'
import type { ReactNode } from 'react'

gsap.registerPlugin(ScrollTrigger, useGSAP)

function reducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export function GsapReveal({
  children,
  delay = 0,
  y = 28,
  className,
}: {
  children: ReactNode
  delay?: number
  y?: number
  className?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  useGSAP(
    () => {
      if (!ref.current || reducedMotion()) return
      const tween = gsap.fromTo(
        ref.current,
        { opacity: 0, y },
        {
          opacity: 1,
          y: 0,
          duration: 0.9,
          delay,
          ease: 'power3.out',
          clearProps: 'transform',
          scrollTrigger: { trigger: ref.current, start: 'top 88%', once: true },
        },
      )
      return () => {
        tween.scrollTrigger?.kill()
        tween.kill()
      }
    },
    { scope: ref, dependencies: [delay, y] },
  )
  return (
    <div ref={ref} className={`gsap-fade ${className ?? ''}`}>
      {children}
    </div>
  )
}

export function ScaleFadeImg({
  src,
  alt,
  seed,
  className,
  aspect = 'aspect-[16/9]',
}: {
  src?: string
  alt: string
  seed: string
  className?: string
  aspect?: string
}) {
  const ref = useRef<HTMLImageElement>(null)
  const url = src ?? `https://picsum.photos/seed/${seed}/1920/1080`
  useGSAP(
    () => {
      if (!ref.current || reducedMotion()) return
      const tween = gsap.fromTo(
        ref.current,
        { scale: 0.85, opacity: 0.4, filter: 'grayscale(50%) contrast(1.1)' },
        {
          scale: 1.0,
          opacity: 1,
          ease: 'none',
          scrollTrigger: { trigger: ref.current, start: 'top 95%', end: 'top 35%', scrub: 1 },
        },
      )
      const fade = gsap.to(ref.current, {
        opacity: 0.3,
        ease: 'none',
        scrollTrigger: { trigger: ref.current, start: 'center 40%', end: 'bottom top', scrub: 1 },
      })
      return () => {
        tween.scrollTrigger?.kill()
        tween.kill()
        fade.scrollTrigger?.kill()
        fade.kill()
      }
    },
    { scope: ref },
  )
  return (
    <div className={`group overflow-hidden border border-line bg-ink-950 ${className ?? ''}`}>
      <img
        ref={ref}
        src={url}
        alt={alt}
        width={1920}
        height={1080}
        loading="lazy"
        className={`${aspect} w-full object-cover opacity-90 contrast-125 grayscale-[30%] transition-transform duration-700 ease-out group-hover:scale-105`}
      />
    </div>
  )
}

export function ScrubWords({ text, className }: { text: string; className?: string }) {
  const ref = useRef<HTMLParagraphElement>(null)
  const words = text.split(' ')
  useGSAP(
    () => {
      if (!ref.current || reducedMotion()) return
      const spans = ref.current.querySelectorAll('[data-word]')
      const tween = gsap.fromTo(
        spans,
        { opacity: 0.1 },
        {
          opacity: 1,
          stagger: 0.06,
          ease: 'none',
          scrollTrigger: { trigger: ref.current, start: 'top 80%', end: 'bottom 45%', scrub: 1 },
        },
      )
      return () => {
        tween.scrollTrigger?.kill()
        tween.kill()
      }
    },
    { scope: ref },
  )
  return (
    <p ref={ref} className={className}>
      {words.map((w, i) => (
        <span key={i} data-word className="inline-block">
          {w}
          {i < words.length - 1 ? '\u00A0' : ''}
        </span>
      ))}
    </p>
  )
}
