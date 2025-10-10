# UI Components Library

재사용 가능한 UI 컴포넌트 라이브러리입니다.

## 📦 설치

모든 컴포넌트는 `components/ui`에서 import할 수 있습니다:

```jsx
import {
  StandardDialog,
  PageHeader,
  ActionButton,
  useNotification
} from '@/components/ui';
```

## 🎨 컴포넌트 목록

### 1. StandardDialog (다이얼로그)

표준 다이얼로그 컴포넌트

```jsx
<StandardDialog
  open={open}
  onClose={handleClose}
  title="제목"
  titleIcon={<Settings />}
  maxWidth="md"
  minHeight="400px"
  showCloseIcon={true}
  actions={[
    { label: '취소', onClick: handleClose },
    { label: '저장', onClick: handleSave, variant: 'contained', loading: saving }
  ]}
>
  <div>다이얼로그 내용</div>
</StandardDialog>
```

**Props:**
- `open`: boolean - 열림 상태
- `onClose`: function - 닫기 핸들러
- `title`: string - 제목
- `titleIcon`: ReactNode - 제목 아이콘
- `maxWidth`: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
- `minHeight`: string | number
- `showCloseIcon`: boolean
- `actions`: Array - 액션 버튼 배열

---

### 2. PageHeader (페이지 헤더)

페이지 상단 헤더

```jsx
<PageHeader
  title="대시보드"
  subtitle="전자두뇌비서관에 오신 것을 환영합니다"
  icon={<Dashboard />}
  actions={
    <Button variant="contained">새로 만들기</Button>
  }
/>
```

**Props:**
- `title`: string - 제목
- `subtitle`: string - 부제목
- `icon`: ReactNode - 아이콘
- `actions`: ReactNode - 오른쪽 액션
- `mb`: number - 하단 마진

---

### 3. ActionButton (액션 버튼)

향상된 액션 버튼

```jsx
<ActionButton
  variant="primary"
  icon={<Save />}
  loading={saving}
  tooltip="저장하기"
  onClick={handleSave}
>
  저장
</ActionButton>
```

**Props:**
- `variant`: 'primary' | 'secondary' | 'danger' | 'outlined' | 'text'
- `loading`: boolean
- `icon`: ReactNode
- `tooltip`: string
- `customColor`: string
- `onClick`: function

**Variants:**
- `primary`: 파란색 contained 버튼
- `secondary`: 파란색 outlined 버튼
- `danger`: 빨간색 contained 버튼

---

### 4. ActionButtonGroup (액션 버튼 그룹)

아이콘 버튼 그룹

```jsx
<ActionButtonGroup
  actions={[
    { icon: <Edit />, onClick: handleEdit, tooltip: '수정' },
    { icon: <Delete />, onClick: handleDelete, tooltip: '삭제', color: 'error' },
    { icon: <Share />, onClick: handleShare, tooltip: '공유' }
  ]}
  size="small"
  gap={1}
/>
```

**Props:**
- `actions`: Array - 액션 배열
- `size`: 'small' | 'medium' | 'large'
- `gap`: number
- `direction`: 'row' | 'column'

---

### 5. LoadingState (로딩 상태)

다양한 로딩 상태 표시

```jsx
// Full Page Loading
<LoadingState loading={loading} type="fullPage" message="로딩 중...">
  <Content />
</LoadingState>

// Inline Loading
<LoadingState loading={loading} type="inline">
  <Content />
</LoadingState>

// Button Loading
{loading ? <LoadingState type="button" size={20} /> : '제출'}

// Skeleton Loading
<LoadingState loading={loading} type="skeleton" skeletonCount={5} skeletonHeight={80} />
```

**Props:**
- `loading`: boolean
- `type`: 'fullPage' | 'inline' | 'button' | 'skeleton'
- `message`: string
- `size`: number
- `skeletonCount`: number
- `skeletonHeight`: number

---

### 6. EmptyState (빈 상태)

빈 상태 표시

```jsx
<EmptyState
  icon={Inbox}
  message="등록된 원고가 없습니다"
  action={
    <Button variant="contained" onClick={handleCreate}>
      새 원고 만들기
    </Button>
  }
/>
```

**Props:**
- `icon`: ReactNode | Component
- `message`: string
- `action`: ReactNode
- `iconSize`: number
- `py`: number

---

### 7. StatusChip (상태 칩)

상태 표시 칩

```jsx
<StatusChip status="published" />
<StatusChip status="draft" label="초안 상태" />
<StatusChip
  status="custom"
  label="커스텀"
  customColors={{ custom: 'success' }}
/>
```

**Props:**
- `status`: string
- `label`: string
- `size`: 'small' | 'medium'
- `variant`: 'outlined' | 'filled'
- `customColors`: object

**기본 상태:**
- `published` → 초록색 (발행됨)
- `draft` → 회색 (초안)
- `pending` → 주황색 (대기 중)
- `active` → 초록색 (활성)
- `error` → 빨간색 (오류)

---

### 8. ContentCard (콘텐츠 카드)

콘텐츠 카드

```jsx
<ContentCard
  title="최근 활동"
  titleIcon={<History />}
  headerAction={<IconButton><Refresh /></IconButton>}
  padding={3}
  transparent={false}
>
  <div>카드 내용</div>
</ContentCard>
```

**Props:**
- `title`: string
- `titleIcon`: ReactNode
- `headerAction`: ReactNode
- `padding`: 2 | 3
- `transparent`: boolean
- `elevation`: number

---

### 9. NotificationSnackbar (알림 스낵바)

알림 표시

```jsx
// 기본 사용
<NotificationSnackbar
  open={snack.open}
  onClose={handleClose}
  message="저장되었습니다"
  severity="success"
/>

// 훅 사용 (추천)
const { notification, showNotification, hideNotification } = useNotification();

showNotification('저장되었습니다!', 'success');
showNotification('오류가 발생했습니다', 'error');

<NotificationSnackbar
  open={notification.open}
  onClose={hideNotification}
  message={notification.message}
  severity={notification.severity}
/>
```

**Props:**
- `open`: boolean
- `onClose`: function
- `message`: string
- `severity`: 'success' | 'error' | 'warning' | 'info'
- `autoHideDuration`: number (ms)
- `position`: { vertical, horizontal }

---

### 10. FormFieldGroup (폼 필드 그룹)

폼 필드 그룹

```jsx
<FormFieldGroup
  fields={[
    {
      type: 'text',
      name: 'name',
      label: '이름',
      value: name,
      onChange: (e) => setName(e.target.value),
      xs: 12,
      sm: 6,
      required: true
    },
    {
      type: 'select',
      name: 'status',
      label: '상태',
      value: status,
      onChange: (e) => setStatus(e.target.value),
      options: [
        { value: 'active', label: '활성' },
        { value: 'inactive', label: '비활성' }
      ],
      xs: 12,
      sm: 6
    },
    {
      type: 'text',
      name: 'description',
      label: '설명',
      value: description,
      onChange: (e) => setDescription(e.target.value),
      xs: 12,
      multiline: true,
      rows: 4
    }
  ]}
  spacing={3}
/>
```

**Field Props:**
- `type`: 'text' | 'select' | 'number' | 'email' | 'password'
- `name`: string
- `label`: string
- `value`: any
- `onChange`: function
- `options`: Array (for select)
- `xs`, `sm`, `md`: Grid sizes
- `required`: boolean
- `disabled`: boolean
- `error`: boolean
- `helperText`: string
- `multiline`: boolean
- `rows`: number

---

## 🎯 사용 예제

### 예제 1: 간단한 페이지

```jsx
import { PageHeader, ContentCard, EmptyState, ActionButton } from '@/components/ui';
import { Dashboard, Add } from '@mui/icons-material';

function MyPage() {
  return (
    <>
      <PageHeader
        title="내 페이지"
        subtitle="페이지 설명"
        icon={<Dashboard />}
        actions={
          <ActionButton variant="primary" icon={<Add />}>
            추가
          </ActionButton>
        }
      />

      <ContentCard title="콘텐츠">
        {items.length === 0 ? (
          <EmptyState message="항목이 없습니다" />
        ) : (
          <List />
        )}
      </ContentCard>
    </>
  );
}
```

### 예제 2: 다이얼로그 with 알림

```jsx
import {
  StandardDialog,
  FormFieldGroup,
  useNotification,
  NotificationSnackbar
} from '@/components/ui';

function MyComponent() {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const { notification, showNotification, hideNotification } = useNotification();

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveData();
      showNotification('저장되었습니다', 'success');
      setOpen(false);
    } catch (error) {
      showNotification('저장 실패: ' + error.message, 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <StandardDialog
        open={open}
        onClose={() => setOpen(false)}
        title="데이터 입력"
        actions={[
          { label: '취소', onClick: () => setOpen(false) },
          { label: '저장', onClick: handleSave, variant: 'contained', loading: saving }
        ]}
      >
        <FormFieldGroup fields={fields} />
      </StandardDialog>

      <NotificationSnackbar
        open={notification.open}
        onClose={hideNotification}
        message={notification.message}
        severity={notification.severity}
      />
    </>
  );
}
```

### 예제 3: 로딩 with 빈 상태

```jsx
import { LoadingState, EmptyState, ContentCard } from '@/components/ui';

function DataList() {
  const { data, loading } = useData();

  return (
    <ContentCard title="데이터 목록">
      <LoadingState loading={loading} type="skeleton" skeletonCount={5}>
        {data.length === 0 ? (
          <EmptyState
            message="데이터가 없습니다"
            action={<Button>데이터 가져오기</Button>}
          />
        ) : (
          <List data={data} />
        )}
      </LoadingState>
    </ContentCard>
  );
}
```

---

## 📁 폴더 구조

```
components/ui/
├── dialogs/
│   ├── StandardDialog.jsx
│   └── index.js
├── feedback/
│   ├── LoadingState.jsx
│   ├── EmptyState.jsx
│   ├── NotificationSnackbar.jsx
│   ├── useNotification.js
│   └── index.js
├── layout/
│   ├── PageHeader.jsx
│   ├── ContentCard.jsx
│   └── index.js
├── buttons/
│   ├── ActionButton.jsx
│   ├── ActionButtonGroup.jsx
│   └── index.js
├── data-display/
│   ├── StatusChip.jsx
│   └── index.js
├── forms/
│   ├── FormFieldGroup.jsx
│   └── index.js
├── index.js
└── README.md
```

---

## 🚀 다음 단계

1. 기존 페이지에 점진적으로 적용
2. Storybook 추가 (선택사항)
3. TypeScript 타입 정의 추가 (선택사항)
4. 추가 컴포넌트 작성 (ConfirmDialog, SearchBar, CardGrid 등)

---

## 💡 팁

- 모든 컴포넌트는 MUI 테마를 자동으로 따릅니다
- `sx` prop으로 추가 스타일링 가능
- 컴포넌트는 반응형으로 설계되었습니다
- `useNotification` 훅을 사용하면 알림 관리가 편리합니다
