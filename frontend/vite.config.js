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
          // MUI만 분리 (가장 큰 용량이고 확실한 이익)
          'mui-core': [
            '@mui/material',
            '@emotion/react',
            '@emotion/styled'
          ],
          // 아이콘은 별도 (조건부 로딩 가능)
          'mui-icons': ['@mui/icons-material']
          
          // 🚫 Firebase, React는 우선 분리하지 않음
          // → 측정 후 필요시에만 추가
        },
        
        // 파일명 패턴 최적화
        chunkFileNames: (chunkInfo) => {
          if (chunkInfo.name === 'mui-core') {
            return 'assets/mui-[hash].js';
          }
          if (chunkInfo.name === 'mui-icons') {
            return 'assets/mui-icons-[hash].js';
          }
          return 'assets/[name]-[hash].js';
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