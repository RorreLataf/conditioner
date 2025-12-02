# Direct Mode vs Indirect Mode в таймерах STM32

## Общее описание

В таймерах STM32 (включая STM32G030F6P6) режимы **Direct** и **Indirect** определяют, какой выходной канал управляется конкретным каналом таймера.

## Direct Mode (Прямой режим)

В **Direct Mode** канал таймера напрямую управляет **своим собственным** выходом:

- `TIMx_CH1` → управляет `OC1` (Output Compare 1)
- `TIMx_CH2` → управляет `OC2` (Output Compare 2)
- `TIMx_CH3` → управляет `OC3` (Output Compare 3)
- `TIMx_CH4` → управляет `OC4` (Output Compare 4)

### Пример:
```
TIM1_CH1 (канал 1) → OC1 (выход 1)
```

## Indirect Mode (Непрямой режим)

В **Indirect Mode** канал таймера управляет **дополнительным (complementary) выходом**:

- `TIMx_CH1` → управляет `OC1N` (Output Compare 1N - дополнительный выход)
- `TIMx_CH2` → управляет `OC2N` (Output Compare 2N)
- `TIMx_CH3` → управляет `OC3N` (Output Compare 3N)
- `TIMx_CH4` → управляет `OC4N` (Output Compare 4N)

### Пример:
```
TIM1_CH1 (канал 1) → OC1N (дополнительный выход 1)
```

## Когда используется Indirect Mode?

**Indirect Mode** используется в следующих случаях:

1. **Центрированное выравнивание (Center-Aligned Mode)**
   - При использовании режима выравнивания по центру (CEN = 1, CMS[1:0] ≠ 00)
   - Для правильной работы с дополнительными выходами

2. **Дополнительные выходы (Complementary Outputs)**
   - Когда нужно управлять парой выходов (OCx и OCxN)
   - Например, для управления мостом H-мостом (H-bridge)

3. **Dead-Time Generation**
   - При использовании генерации мертвого времени (dead-time)
   - Для предотвращения короткого замыкания в силовых приложениях

## Регистры управления

### CCER (Capture/Compare Enable Register)

Биты `CCxE` и `CCxNE` управляют режимами:

```c
// Direct Mode
TIMx->CCER |= TIM_CCER_CC1E;        // Включить OC1 (прямой выход)
TIMx->CCER &= ~TIM_CCER_CC1NE;      // Отключить OC1N

// Indirect Mode  
TIMx->CCER &= ~TIM_CCER_CC1E;       // Отключить OC1
TIMx->CCER |= TIM_CCER_CC1NE;       // Включить OC1N (дополнительный выход)
```

### CR1 (Control Register 1)

Биты `CMS[1:0]` определяют режим выравнивания:

```c
// Центрированное выравнивание (может потребовать Indirect Mode)
TIMx->CR1 |= TIM_CR1_CMS_1;         // Center-aligned mode 1
// или
TIMx->CR1 |= TIM_CR1_CMS_0;         // Center-aligned mode 2
// или
TIMx->CR1 |= (TIM_CR1_CMS_1 | TIM_CR1_CMS_0);  // Center-aligned mode 3
```

## Примеры использования

### Пример 1: Direct Mode (обычный PWM)

```c
// Настройка TIM1_CH1 для прямого управления OC1
void TIM1_PWM_Direct_Init(void)
{
    // Включить тактирование
    RCC->APBENR2 |= RCC_APBENR2_TIM1EN;
    
    // Настройка канала 1 как PWM выход
    TIM1->CCMR1 |= TIM_CCMR1_OC1M_2 | TIM_CCMR1_OC1M_1;  // PWM mode 1
    TIM1->CCMR1 |= TIM_CCMR1_OC1PE;                      // Preload enable
    
    // Включить выход OC1 (Direct Mode)
    TIM1->CCER |= TIM_CCER_CC1E;                         // OC1 включен
    TIM1->CCER &= ~TIM_CCER_CC1NE;                      // OC1N отключен
    
    // Включить таймер
    TIM1->CR1 |= TIM_CR1_CEN;
}
```

### Пример 2: Indirect Mode (с дополнительным выходом)

```c
// Настройка TIM1_CH1 для управления OC1N (Indirect Mode)
void TIM1_PWM_Indirect_Init(void)
{
    // Включить тактирование
    RCC->APBENR2 |= RCC_APBENR2_TIM1EN;
    
    // Настройка канала 1 как PWM выход
    TIM1->CCMR1 |= TIM_CCMR1_OC1M_2 | TIM_CCMR1_OC1M_1;  // PWM mode 1
    TIM1->CCMR1 |= TIM_CCMR1_OC1PE;                      // Preload enable
    
    // Включить выход OC1N (Indirect Mode)
    TIM1->CCER &= ~TIM_CCER_CC1E;                       // OC1 отключен
    TIM1->CCER |= TIM_CCER_CC1NE;                       // OC1N включен
    
    // Включить таймер
    TIM1->CR1 |= TIM_CR1_CEN;
}
```

### Пример 3: Центрированное выравнивание (требует Indirect Mode)

```c
// Центрированное выравнивание с Indirect Mode
void TIM1_CenterAligned_Init(void)
{
    // Включить тактирование
    RCC->APBENR2 |= RCC_APBENR2_TIM1EN;
    
    // Настройка канала
    TIM1->CCMR1 |= TIM_CCMR1_OC1M_2 | TIM_CCMR1_OC1M_1;  // PWM mode 1
    TIM1->CCMR1 |= TIM_CCMR1_OC1PE;
    
    // Центрированное выравнивание
    TIM1->CR1 |= TIM_CR1_CMS_1;                         // Center-aligned mode 1
    
    // В этом режиме CH1 управляет OC1N (Indirect Mode)
    TIM1->CCER |= TIM_CCER_CC1NE;                       // OC1N включен
    
    // Включить таймер
    TIM1->CR1 |= TIM_CR1_CEN;
}
```

## Визуальное сравнение

### Direct Mode:
```
TIMx_CH1 ──────► OC1 (прямой выход)
                 
TIMx_CH2 ──────► OC2 (прямой выход)
```

### Indirect Mode:
```
TIMx_CH1 ──────► OC1N (дополнительный выход)
                 
TIMx_CH2 ──────► OC2N (дополнительный выход)
```

### Комбинированный режим (оба выхода):
```
TIMx_CH1 ──────► OC1  (прямой)
                 │
                 └───► OC1N (дополнительный)
```

## Важные замечания

1. **Не все таймеры поддерживают Indirect Mode**
   - Обычно только **TIM1** и **TIM8** (advanced timers) имеют дополнительные выходы
   - **TIM2-TIM7** (general-purpose timers) обычно работают только в Direct Mode

2. **STM32G030F6P6**
   - Имеет TIM1 (advanced timer) с поддержкой дополнительных выходов
   - TIM2, TIM3, TIM14, TIM16, TIM17 - general-purpose timers (только Direct Mode)

3. **Dead-Time**
   - При использовании дополнительных выходов обычно включается генерация мертвого времени
   - Управляется через регистр `BDTR` (Break and Dead-Time Register)

4. **Центрированное выравнивание**
   - В режиме центрированного выравнивания (CMS ≠ 00) каналы автоматически работают в Indirect Mode
   - Это необходимо для правильной синхронизации

## Регистр BDTR (Break and Dead-Time Register)

Для управления мертвым временем между OCx и OCxN:

```c
// Настройка мертвого времени
TIM1->BDTR |= (10 << TIM_BDTR_DTG_Pos);  // Dead-time = 10 тактов
TIM1->BDTR |= TIM_BDTR_MOE;               // Main Output Enable
```

## Как работает выбор режима?

### Логика выбора Direct/Indirect Mode

Режим определяется комбинацией битов в регистре `CCER`:

| CCxE | CCxNE | Режим | Управляемый выход |
|------|-------|-------|-------------------|
| 1    | 0     | Direct | OCx |
| 0    | 1     | Indirect | OCxN |
| 1    | 1     | Оба | OCx и OCxN (с dead-time) |

### Влияние центрированного выравнивания

При центрированном выравнивании (CMS ≠ 00):
- Каналы автоматически переключаются в Indirect Mode
- Это необходимо для правильной синхронизации дополнительных выходов
- Прямые выходы (OCx) могут быть недоступны в этом режиме

## Практические примеры для STM32G030F6P6

### Пример 4: H-мост с двумя выходами (OC1 и OC1N)

```c
// Управление H-мостом с использованием обоих выходов
void TIM1_HBridge_Init(void)
{
    // Включить тактирование
    RCC->APBENR2 |= RCC_APBENR2_TIM1EN;
    
    // Настройка канала 1 как PWM
    TIM1->CCMR1 |= TIM_CCMR1_OC1M_2 | TIM_CCMR1_OC1M_1;  // PWM mode 1
    TIM1->CCMR1 |= TIM_CCMR1_OC1PE;                      // Preload enable
    
    // Настройка мертвого времени (предотвращение короткого замыкания)
    TIM1->BDTR |= (20 << TIM_BDTR_DTG_Pos);              // Dead-time = 20 тактов
    TIM1->BDTR |= TIM_BDTR_MOE;                          // Main Output Enable
    
    // Включить ОБА выхода (OC1 и OC1N)
    TIM1->CCER |= TIM_CCER_CC1E;                         // OC1 включен (Direct)
    TIM1->CCER |= TIM_CCER_CC1NE;                        // OC1N включен (Indirect)
    
    // Настройка частоты PWM
    TIM1->PSC = 0;                                        // Prescaler = 1
    TIM1->ARR = 1000;                                     // Period = 1000
    TIM1->CCR1 = 500;                                     // Duty cycle = 50%
    
    // Включить таймер
    TIM1->CR1 |= TIM_CR1_CEN;
}
```

### Пример 5: Только Indirect Mode (только OC1N)

```c
// Использование только дополнительного выхода
void TIM1_Indirect_Only_Init(void)
{
    RCC->APBENR2 |= RCC_APBENR2_TIM1EN;
    
    // Настройка PWM
    TIM1->CCMR1 |= TIM_CCMR1_OC1M_2 | TIM_CCMR1_OC1M_1;
    TIM1->CCMR1 |= TIM_CCMR1_OC1PE;
    
    // Только Indirect Mode - управляем только OC1N
    TIM1->CCER &= ~TIM_CCER_CC1E;                        // OC1 отключен
    TIM1->CCER |= TIM_CCER_CC1NE;                        // OC1N включен (Indirect)
    
    TIM1->PSC = 0;
    TIM1->ARR = 1000;
    TIM1->CCR1 = 300;                                     // 30% duty cycle
    
    TIM1->CR1 |= TIM_CR1_CEN;
}
```

### Пример 6: Переключение между режимами во время работы

```c
// Переключение между Direct и Indirect Mode
void TIM1_Switch_Mode(uint8_t use_indirect)
{
    if (use_indirect)
    {
        // Переключиться на Indirect Mode
        TIM1->CCER &= ~TIM_CCER_CC1E;                    // Отключить OC1
        TIM1->CCER |= TIM_CCER_CC1NE;                   // Включить OC1N
    }
    else
    {
        // Переключиться на Direct Mode
        TIM1->CCER &= ~TIM_CCER_CC1NE;                  // Отключить OC1N
        TIM1->CCER |= TIM_CCER_CC1E;                    // Включить OC1
    }
}
```

## Временные диаграммы

### Direct Mode (OC1):
```
TIM1_CH1 (CCR1):
    ┌─────┐     ┌─────┐     ┌─────┐
    │     │     │     │     │     │
────┘     └─────┘     └─────┘     └───

OC1 (выход):
    ┌─────┐     ┌─────┐     ┌─────┐
    │     │     │     │     │     │
────┘     └─────┘     └─────┘     └───
```

### Indirect Mode (OC1N):
```
TIM1_CH1 (CCR1):
    ┌─────┐     ┌─────┐     ┌─────┐
    │     │     │     │     │     │
────┘     └─────┘     └─────┘     └───

OC1N (выход, инвертированный):
    ────┐     └─────┐     └─────┐     └───
        │     │     │     │     │
        └─────┘     └─────┘     └─────
```

### Оба выхода с Dead-Time:
```
TIM1_CH1 (CCR1):
    ┌─────┐     ┌─────┐     ┌─────┐
    │     │     │     │     │     │
────┘     └─────┘     └─────┘     └───

OC1:
    ┌─────┐     ┌─────┐     ┌─────┐
    │     │     │     │     │     │
────┘     └─────┘     └─────┘     └───

OC1N:
        ┌─────┐     ┌─────┐     ┌─────┐
        │     │     │     │     │     │
────┐   └─────┘     └─────┘     └─────┘
    │
    └── Dead-Time (защита от короткого замыкания)
```

## Отличия на уровне регистров

### CCER (Capture/Compare Enable Register)

```c
// Позиции битов для канала 1:
// CC1E  - бит 0: Enable для OC1 (Direct)
// CC1NE - бит 2: Enable для OC1N (Indirect)

// Direct Mode:
TIM1->CCER = (1 << 0);  // CC1E = 1, CC1NE = 0

// Indirect Mode:
TIM1->CCER = (1 << 2);   // CC1E = 0, CC1NE = 1

// Оба выхода:
TIM1->CCER = (1 << 0) | (1 << 2);  // CC1E = 1, CC1NE = 1
```

### Влияние на другие регистры

- **CCMR1/CCMR2**: Настройки режима работы (PWM mode, preload) одинаковы для обоих режимов
- **CCR1-CCR4**: Значения сравнения используются для обоих выходов
- **BDTR**: Dead-time применяется только когда оба выхода включены (CCxE=1 и CCxNE=1)

## Когда использовать каждый режим?

### Direct Mode используется для:
- ✅ Простых PWM сигналов
- ✅ Управления светодиодами
- ✅ Генерации звука
- ✅ Управления сервоприводами
- ✅ Любых приложений, где нужен один выход

### Indirect Mode используется для:
- ✅ Управления H-мостом (вместе с Direct)
- ✅ Центрированного выравнивания PWM
- ✅ Синхронизации нескольких выходов
- ✅ Приложений, требующих дополнительных выходов

### Оба режима одновременно:
- ✅ H-мост с защитой от короткого замыкания (dead-time)
- ✅ Двухтактные преобразователи
- ✅ Управление двигателями с реверсом

## Резюме

| Параметр | Direct Mode | Indirect Mode |
|----------|-------------|---------------|
| **Управляемый выход** | OCx (прямой) | OCxN (дополнительный) |
| **Бит в CCER** | CCxE = 1 | CCxNE = 1 |
| **Использование** | Обычный PWM | Дополнительные выходы, H-bridge |
| **Центрированное выравнивание** | Не требуется | Обычно требуется |
| **Dead-Time** | Не требуется | Обычно используется |
| **Поддержка таймеров** | Все таймеры | Только TIM1, TIM8 (advanced) |
| **Инверсия сигнала** | Нет | Да (относительно Direct) |
| **Синхронизация** | Не требуется | Может требовать синхронизации с OCx |

## Часто задаваемые вопросы

**Q: Можно ли использовать Direct и Indirect одновременно?**  
A: Да, установив оба бита CCxE и CCxNE. В этом случае оба выхода активны, но с мертвым временем между ними.

**Q: Почему Indirect Mode доступен только на TIM1?**  
A: Только advanced timers (TIM1, TIM8) имеют дополнительные выходы OCxN. General-purpose timers имеют только прямые выходы OCx.

**Q: Нужно ли менять настройки CCRx при переключении режимов?**  
A: Нет, значение CCRx используется для обоих выходов. Меняется только то, какой выход управляется.

**Q: Как работает инверсия в Indirect Mode?**  
A: OCxN инвертирован относительно OCx. Когда OCx высокий, OCxN низкий, и наоборот (с учетом dead-time).
