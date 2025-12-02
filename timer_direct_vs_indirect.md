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

## Резюме

| Параметр | Direct Mode | Indirect Mode |
|----------|-------------|---------------|
| **Управляемый выход** | OCx (прямой) | OCxN (дополнительный) |
| **Использование** | Обычный PWM | Дополнительные выходы, H-bridge |
| **Центрированное выравнивание** | Не требуется | Обычно требуется |
| **Dead-Time** | Не требуется | Обычно используется |
| **Поддержка таймеров** | Все таймеры | Только TIM1, TIM8 (advanced) |
