# Firebase Email Extension 설치 가이드

## 1. Extension 설치

```bash
# Firebase CLI로 설치
firebase ext:install firestore-send-email

# 또는 Firebase Console에서 설치:
# https://console.firebase.google.com/project/_/extensions
```

## 2. 설치 시 설정 값

Extension 설치 중 다음 정보를 입력해야 합니다:

```
SMTP 연결 URI:
- Gmail 사용: smtps://username@gmail.com:password@smtp.gmail.com:465
- SendGrid 사용: smtps://apikey:YOUR_SENDGRID_API_KEY@smtp.sendgrid.net:465

Email 문서 컬렉션: mail
기본 FROM 주소: noreply@yourdomain.com
사용자 정의 템플릿 디렉토리: (비워두기)
```

### Gmail 앱 비밀번호 생성 (Gmail 사용 시)

1. Google 계정 → 보안 → 2단계 인증 활성화
2. 보안 → 앱 비밀번호 생성
3. '앱 선택' → 기타(맞춤 이름) → "Firebase Email"
4. 생성된 16자리 비밀번호 복사

SMTP URI 예시:
```
smtps://yourname@gmail.com:abcd-efgh-ijkl-mnop@smtp.gmail.com:465
```

## 3. 환경 변수 설정 (권장)

민감 정보는 Firebase 환경 변수로 관리:

```bash
# SMTP 정보를 환경 변수로 설정
firebase functions:config:set email.smtp_uri="smtps://..."

# 확인
firebase functions:config:get
```

## 4. 테스트 이메일 발송

Firestore에서 직접 문서 추가:

```javascript
await db.collection('mail').add({
  to: 'test@example.com',
  message: {
    subject: '테스트 이메일',
    text: '이것은 테스트 이메일입니다.',
    html: '<h1>테스트</h1><p>이것은 테스트 이메일입니다.</p>'
  }
});
```

## 5. 이메일 템플릿 작성

`functions/email-templates/` 디렉토리에 HTML 템플릿 저장:

```html
<!-- priority-gained.html -->
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
    .container { max-width: 600px; margin: 0 auto; padding: 20px; }
    .header { background: #4CAF50; color: white; padding: 20px; border-radius: 8px 8px 0 0; }
    .content { background: #f9f9f9; padding: 30px; border-radius: 0 0 8px 8px; }
    .button { background: #4CAF50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; display: inline-block; margin-top: 20px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>🎉 우선권 획득 안내</h1>
    </div>
    <div class="content">
      <p>안녕하세요, <strong>{{userName}}</strong>님!</p>

      <p>좋은 소식이 있습니다.</p>

      <p><strong>{{districtName}}</strong> 선거구의 우선권을 획득하셨습니다.</p>

      <p>이제 월 90회 콘텐츠 생성 서비스를 제한 없이 이용하실 수 있습니다.</p>

      <a href="{{loginUrl}}" class="button">지금 시작하기</a>

      <hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">

      <p style="color: #666; font-size: 12px;">
        이 이메일은 자동으로 발송되었습니다.<br>
        문의사항이 있으시면 support@yourdomain.com으로 연락주세요.
      </p>
    </div>
  </div>
</body>
</html>
```

## 6. 발송 상태 확인

Extension이 자동으로 delivery 필드 업데이트:

```javascript
{
  to: 'user@example.com',
  message: { ... },

  // Extension이 자동 추가
  delivery: {
    state: 'SUCCESS' | 'ERROR' | 'PENDING',
    startTime: Timestamp,
    endTime: Timestamp,
    error: string,  // 실패 시
    info: {
      messageId: 'xxx',
      accepted: ['user@example.com'],
      rejected: [],
      response: '250 OK'
    }
  }
}
```

## 7. 문제 해결

### 이메일이 발송되지 않는 경우

1. Firebase Console → Functions → 로그 확인
2. mail 컬렉션에서 delivery.state 확인
3. SMTP 인증 정보 재확인

### Gmail "보안 수준이 낮은 앱" 오류

- 앱 비밀번호를 사용하세요 (위 2단계 참조)
- 일반 비밀번호는 작동하지 않습니다

### SendGrid 사용 시

```bash
# SendGrid API 키 생성:
# https://app.sendgrid.com/settings/api_keys

# SMTP URI:
smtps://apikey:SG.xxxxxxxxxxxxxx@smtp.sendgrid.net:465
```

## 8. 비용

- 무료: 월 5,000통까지
- 이후: Cloud Functions 실행 비용만 발생 (매우 저렴)
- SMTP 서비스 비용은 별도 (Gmail은 무료)

## 참고 자료

- [공식 문서](https://extensions.dev/extensions/firebase/firestore-send-email)
- [GitHub](https://github.com/firebase/extensions/tree/master/firestore-send-email)
