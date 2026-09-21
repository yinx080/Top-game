const MIN_SECONDS = 1.2 // the strong motion ends ~0.9 s; this lets it settle

const appPainted = () =>
  document.fonts.ready.then(
    () => new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r()))),
  )

function playedFor(video: HTMLVideoElement, seconds: number, timeoutMs: number) {
  return new Promise<void>((resolve) => {
    const done = () => {
      clearTimeout(timer)
      video.removeEventListener('timeupdate', check)
      resolve()
    }
    const check = () => { if (video.currentTime >= seconds || video.ended) done() }
    const timer = setTimeout(done, timeoutMs)
    video.addEventListener('timeupdate', check)
    check()
  })
}

export async function dismissBoot() {
  const boot = document.getElementById('boot')
  if (!boot) return
  const video = boot.querySelector('video')
  await appPainted()
  // If the video never started (autoplay blocked, slow network), don't wait for it.
  if (video && video.currentTime > 0) await playedFor(video, MIN_SECONDS, 1500)
  boot.classList.add('is-hiding')
  setTimeout(() => boot.remove(), 500)
}