# Parallax Cards Debug Test Validation

## Problem Summary
All 3 cards were showing simultaneously on desktop instead of one at a time.

## Root Causes Identified

### 1. **Callback Dependency Issue**
- `updateScrollProgress` had `activeCard` as dependency
- This caused the callback to recreate on every state change
- Led to render loops and stale closures

### 2. **Conditional Rendering Logic**
- The `return null` was working, but timing issues existed
- Need explicit opacity/visibility control for smoother transitions

### 3. **State Update Pattern**
- Direct state updates caused unnecessary re-renders
- Needed conditional updates only when value actually changes

## Fixes Applied

### 1. **Removed Callback Dependencies**
```javascript
// BEFORE:
const updateScrollProgress = React.useCallback(() => {
  // ... logic
}, [activeCard]); // ❌ Causes re-creation

// AFTER:
const updateScrollProgress = React.useCallback(() => {
  // ... logic
}, []); // ✅ Stable callback
```

### 2. **Conditional State Updates**
```javascript
// BEFORE:
setActiveCard(newActiveCard); // ❌ Always updates

// AFTER:
setActiveCard(prevActive => {
  if (prevActive !== newActiveCard) {
    return newActiveCard; // ✅ Only update if changed
  }
  return prevActive;
});
```

### 3. **Enhanced Visibility Control**
```javascript
// BEFORE:
opacity: 1,

// AFTER:
opacity: isActive ? 1 : (isMobile ? 1 : 0),
visibility: isActive ? 'visible' : (isMobile ? 'visible' : 'hidden'),
```

### 4. **Simplified Card Transition Logic**
```javascript
// BEFORE: Complex loop with edge cases
const cardTransitionPoints = [0, 0.33, 0.66, 1.0];
for (let i = 0; i < cardTransitionPoints.length - 1; i++) {
  // Complex logic with potential for bugs
}

// AFTER: Simple and explicit
let newActiveCard = 0;
if (progress >= 0.33 && progress < 0.66) {
  newActiveCard = 1;
} else if (progress >= 0.66) {
  newActiveCard = 2;
}
```

## Testing Checklist

### Desktop Testing
- [ ] Only one card visible at a time
- [ ] Card transitions happen at 33% and 66% scroll progress
- [ ] No visual glitches during transitions
- [ ] Smooth opacity/visibility changes
- [ ] Debug panel shows correct active card
- [ ] Console logs show proper render/non-render decisions

### Mobile Testing
- [ ] All 3 cards visible stacked vertically
- [ ] No absolute positioning conflicts
- [ ] Proper spacing between cards
- [ ] No scroll-based transitions (static display)

### Debug Features
- [ ] Enhanced debug panel shows:
  - Current active card
  - Mobile/desktop state
  - Scroll progress percentage
  - Which cards should be visible
  - Transition breakpoints
- [ ] Console logs show:
  - Card render decisions
  - State transitions
  - Timing information

## Browser Console Commands for Testing

```javascript
// Test isMobile detection
console.log('isMobile:', window.innerWidth < 900);

// Monitor activeCard state
// (Check React DevTools Component tab)

// Test scroll progress calculation
window.addEventListener('scroll', () => {
  const section = document.querySelector('[aria-labelledby="urgency-heading"]');
  if (section) {
    const rect = section.getBoundingClientRect();
    const progress = Math.max(0, Math.min(1,
      (window.innerHeight - rect.top) / (section.offsetHeight + window.innerHeight)
    ));
    console.log('Manual progress calculation:', progress);
  }
});
```

## Expected Behavior

### Desktop (md breakpoint and above)
1. **Scroll Progress 0-33%**: Card 1 (이재명) visible, others hidden
2. **Scroll Progress 33-66%**: Card 2 (트럼프) visible, others hidden
3. **Scroll Progress 66-100%**: Card 3 (정청래) visible, others hidden

### Mobile (below md breakpoint)
1. All 3 cards visible simultaneously
2. Stacked vertically with proper spacing
3. No scroll-based transitions

## Performance Improvements
- Reduced unnecessary re-renders
- Eliminated callback recreation cycles
- Optimized conditional rendering logic
- Better event handling with passive scroll listeners

## Debugging Tools Added
- Visual card borders in development mode
- Enhanced debug panel with real-time data
- Detailed console logging for render decisions
- Transition timing information