import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { visualizer } from 'rollup-plugin-visualizer'

export default defineConfig({
  plugins: [
    react(),
    // 번들 분석기 - npm run build 후 stats.html 생성
    visualizer({
      filename: 'stats.html',
      gzipSize: true,
      brotliSize: true,
      template: 'treemap'
    })
  ],
  
  // 🔧 코드 스플릿 최적화
  build: {
    // 청크 크기 경고 임계값 조정
    chunkSizeWarningLimit: 1000,
    
    rollupOptions: {
      output: {
        // 🎯 핵심: 측정 후 최소한만 분리 (워터폴 방지)
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'firebase': [
            'firebase/app', 'firebase/auth', 'firebase/firestore',
            'firebase/functions', 'firebase/storage'
          ],
          'mui-core': [
            '@mui/material', '@emotion/react', '@emotion/styled'
          ],
          'mui-icons': ['@mui/icons-material'],
          'charts': ['recharts'],
          'motion': ['framer-motion']
        }
      }
    },
    
    // esbuild minify 사용 (더 빠름)
    minify: true,
  },
  
  // 개발 서버 최적화
  server: {
    fs: {
      strict: false
    }
  }
})