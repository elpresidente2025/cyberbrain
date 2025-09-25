module.exports = {
  root: true,
  env: {
    es6: true,
    node: true,
    es2020: true,
  },
  extends: [
    "eslint:recommended",
  ],
  parserOptions: {
    ecmaVersion: 2020,
    sourceType: 'module',
  },
  rules: {
    // 🔧 개선: 사용되지 않는 변수 처리 (언더스코어 접두사 허용)
    "no-unused-vars": ["warn", { 
      "vars": "all",
      "args": "none",           // 함수 파라미터는 체크 안함
      "ignoreRestSiblings": true,
      "argsIgnorePattern": "^_", // _로 시작하는 변수는 무시
      "varsIgnorePattern": "^_"  // _로 시작하는 변수는 무시
    }],
    
    // 🔧 개선: Firebase Functions에서 유용한 기본 규칙들 활성화
    "no-undef": "error",           // 정의되지 않은 변수 사용 금지
    "no-redeclare": "error",       // 변수 재선언 금지
    "no-unreachable": "error",     // 도달할 수 없는 코드 금지
    "no-constant-condition": "warn", // 상수 조건문 경고
    "no-empty": "warn",            // 빈 블록 경고
    "no-extra-semi": "warn",       // 불필요한 세미콜론 경고
    "no-func-assign": "error",     // 함수 재할당 금지
    "no-irregular-whitespace": "error", // 비정상적인 공백 금지
    "no-obj-calls": "error",       // 객체를 함수로 호출 금지
    "valid-typeof": "error",       // typeof 연산자 올바른 사용
    
    // 🔧 개선: Firebase Functions 특화 규칙
    "prefer-const": "warn",        // const 사용 권장
    "no-var": "warn",             // var 사용 금지 (let, const 사용)
    "eqeqeq": ["warn", "always"],  // === 사용 권장
    "no-eval": "error",           // eval 사용 금지
    "no-implied-eval": "error",   // 암시적 eval 금지
    "no-new-func": "error",       // Function 생성자 사용 금지
    
    // 🔧 개선: 에러 처리 관련
    "no-throw-literal": "error",   // throw에 리터럴 사용 금지
    "prefer-promise-reject-errors": "warn", // Promise.reject에 Error 객체 사용 권장
    
    // Firebase Functions에서 허용하는 규칙들
    "quotes": "off",
    "semi": "off",
    "comma-dangle": "off",
    "no-console": "off",          // Firebase Functions에서는 console.log 필요
    "indent": "off",
    "object-curly-spacing": "off",
    "max-len": "off",
    "require-jsdoc": "off",
    "valid-jsdoc": "off",
    "camelcase": "off",
    "new-cap": "off",
    "no-trailing-spaces": "off",
    "padded-blocks": "off",
    "space-before-function-paren": "off",
    "keyword-spacing": "off",
    "space-infix-ops": "off",
    "eol-last": "off",
    "no-multiple-empty-lines": "off",
    "brace-style": "off",
    "curly": "off",
    "no-restricted-globals": "off",
    "prefer-arrow-callback": "off",
  },
  
  // 🔧 추가: Firebase Functions 특화 설정
  overrides: [
    {
      files: ["scripts/**/*.js"],
      rules: {
        "no-console": "off",      // 스크립트에서는 console 완전 허용
        "no-process-exit": "off", // 스크립트에서는 process.exit 허용
      }
    },
    {
      files: ["handlers/**/*.js"],
      rules: {
        "prefer-const": "error",  // 핸들러에서는 const 사용 강제
      }
    }
  ],
  
  // 🔧 추가: 글로벌 변수 정의 (Firebase Functions 환경)
  globals: {
    "console": "readonly",
    "process": "readonly",
    "Buffer": "readonly",
    "__dirname": "readonly",
    "__filename": "readonly",
    "module": "readonly",
    "require": "readonly",
    "exports": "readonly",
    "global": "readonly",
  }
};