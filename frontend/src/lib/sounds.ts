// Sound effects for the app
// Using Web Audio API for lightweight, instant sounds

let audioContext: AudioContext | null = null

function getAudioContext(): AudioContext {
  if (!audioContext) {
    audioContext = new AudioContext()
  }
  return audioContext
}

// Check if sounds are enabled
function isSoundEnabled(): boolean {
  return localStorage.getItem('soundEnabled') !== 'false'
}

export function setSoundEnabled(enabled: boolean): void {
  localStorage.setItem('soundEnabled', enabled ? 'true' : 'false')
}

export function getSoundEnabled(): boolean {
  return isSoundEnabled()
}

// Gentle notification sound - soft chime
export function playMessageComplete(): void {
  if (!isSoundEnabled()) return
  try {
    const ctx = getAudioContext()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    
    osc.connect(gain)
    gain.connect(ctx.destination)
    
    osc.frequency.setValueAtTime(880, ctx.currentTime) // A5
    osc.frequency.setValueAtTime(1100, ctx.currentTime + 0.1) // C#6
    
    gain.gain.setValueAtTime(0.1, ctx.currentTime)
    gain.gain.setTargetAtTime(0.01, ctx.currentTime, 0.1)
    
    osc.start(ctx.currentTime)
    osc.stop(ctx.currentTime + 0.3)
  } catch {
    // Audio not available
  }
}

// Subtle click for interactions
export function playClick(): void {
  if (!isSoundEnabled()) return
  try {
    const ctx = getAudioContext()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    
    osc.connect(gain)
    gain.connect(ctx.destination)
    
    osc.frequency.setValueAtTime(600, ctx.currentTime)
    gain.gain.setValueAtTime(0.05, ctx.currentTime)
    gain.gain.setTargetAtTime(0.001, ctx.currentTime, 0.02)
    
    osc.start(ctx.currentTime)
    osc.stop(ctx.currentTime + 0.05)
  } catch {
    // Audio not available
  }
}

// Success sound - ascending notes
export function playSuccess(): void {
  if (!isSoundEnabled()) return
  try {
    const ctx = getAudioContext()
    const notes = [523, 659, 784] // C5, E5, G5
    
    notes.forEach((freq, i) => {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      
      osc.connect(gain)
      gain.connect(ctx.destination)
      
      const time = ctx.currentTime + i * 0.1
      osc.frequency.setValueAtTime(freq, time)
      gain.gain.setValueAtTime(0.08, time)
      gain.gain.setTargetAtTime(0.001, time, 0.1)
      
      osc.start(time)
      osc.stop(time + 0.15)
    })
  } catch {
    // Audio not available
  }
}

// Error sound - low tone
export function playError(): void {
  if (!isSoundEnabled()) return
  try {
    const ctx = getAudioContext()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    
    osc.connect(gain)
    gain.connect(ctx.destination)
    
    osc.type = 'sine'
    osc.frequency.setValueAtTime(200, ctx.currentTime)
    osc.frequency.setValueAtTime(150, ctx.currentTime + 0.1)
    
    gain.gain.setValueAtTime(0.1, ctx.currentTime)
    gain.gain.setTargetAtTime(0.001, ctx.currentTime, 0.15)
    
    osc.start(ctx.currentTime)
    osc.stop(ctx.currentTime + 0.25)
  } catch {
    // Audio not available
  }
}
