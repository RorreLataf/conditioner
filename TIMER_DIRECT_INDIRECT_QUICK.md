# Direct vs Indirect Mode - Краткая справка

## 🎯 Главное отличие

**Direct Mode**: Канал таймера → управляет **OCx** (прямой выход)  
**Indirect Mode**: Канал таймера → управляет **OCxN** (дополнительный выход)

## 📊 Визуально

```
Direct Mode:
TIM1_CH1 ────► OC1  (прямой выход)

Indirect Mode:
TIM1_CH1 ────► OC1N (дополнительный выход)
```

## ⚙️ Управление через регистр CCER

```c
// Direct Mode
TIM1->CCER |= TIM_CCER_CC1E;        // OC1 включен
TIM1->CCER &= ~TIM_CCER_CC1NE;      // OC1N отключен

// Indirect Mode
TIM1->CCER &= ~TIM_CCER_CC1E;       // OC1 отключен
TIM1->CCER |= TIM_CCER_CC1NE;       // OC1N включен

// Оба выхода (H-мост)
TIM1->CCER |= TIM_CCER_CC1E;        // OC1 включен
TIM1->CCER |= TIM_CCER_CC1NE;       // OC1N включен
// + настройка Dead-Time в BDTR
```

## 🔑 Ключевые моменты

| | Direct | Indirect |
|---|---|---|
| **Выход** | OCx | OCxN |
| **Бит CCER** | CCxE | CCxNE |
| **Поддержка** | Все таймеры | Только TIM1, TIM8 |
| **Использование** | Обычный PWM | H-bridge, центрированное выравнивание |

## 💡 Когда что использовать?

- **Direct**: Простой PWM, светодиоды, сервоприводы
- **Indirect**: H-мост, центрированное выравнивание, дополнительные выходы
- **Оба**: H-мост с защитой (dead-time)

## ⚠️ Важно

1. Indirect Mode доступен только на **TIM1** и **TIM8** (advanced timers)
2. При центрированном выравнивании (CMS ≠ 00) обычно используется Indirect Mode
3. Для H-моста нужен Dead-Time (регистр BDTR) для защиты от короткого замыкания
