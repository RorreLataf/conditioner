/**
 * @file stm32g030_adc_simple.c
 * @brief Упрощенный пример использования АЦП STM32G030F6P6 с CMSIS
 * 
 * Этот вариант использует прямую запись в регистры для максимальной совместимости
 */

#include "stm32g0xx.h"

/**
 * @brief Инициализация АЦП для одиночного преобразования на канале 0 (PA0)
 * 
 * Проверено по RM0444 для STM32G0
 */
void ADC1_Init_Single_PA0(void)
{
    /* 1. Включение тактирования */
    RCC->IOPENR |= RCC_IOPENR_GPIOAEN;      // GPIOA clock
    RCC->AHBENR |= RCC_AHBENR_ADCEN;        // ADC clock
    __NOP(); __NOP(); __NOP();              // Небольшая задержка
    
    /* 2. Настройка PA0 в аналоговый режим */
    // MODER[1:0] для PA0 = 11 (аналоговый режим)
    GPIOA->MODER &= ~(0x3UL << (0 * 2));    // Очистить биты MODER[1:0]
    GPIOA->MODER |=  (0x3UL << (0 * 2));    // Установить 11 (аналоговый)
    
    // Отключить подтяжки
    GPIOA->PUPDR &= ~(0x3UL << (0 * 2));
    
    /* 3. Отключение ADC, если был включен */
    if (ADC1->CR & ADC_CR_ADEN)
    {
        ADC1->CR |= ADC_CR_ADDIS;
        while (ADC1->CR & ADC_CR_ADEN) { __NOP(); }
    }
    
    /* 4. Включение регулятора напряжения ADC */
    ADC1->CR |= ADC_CR_ADVREGEN;
    
    // Задержка стабилизации регулятора (~10 мкс минимум)
    // Для 16 МГц: ~160 тактов, используем 200 с запасом
    for (volatile uint32_t i = 0; i < 200; i++) { __NOP(); }
    
    /* 5. Калибровка ADC */
    ADC1->CR |= ADC_CR_ADCAL;
    while (ADC1->CR & ADC_CR_ADCAL) { __NOP(); }
    
    /* 6. Настройка параметров ADC */
    
    // 6.1. Источник тактирования: синхронный PCLK/2
    // CKMODE[1:0] = 01
    ADC1->CFGR2 &= ~(0x3UL << 30);          // Очистить CKMODE[1:0]
    ADC1->CFGR2 |=  (0x1UL << 30);          // Установить 01 (PCLK/2)
    
    // 6.2. Время выборки: максимальное (640.5 циклов)
    // SMP[2:0] = 111
    ADC1->SMPR = (7UL << 0);                 // 111 в битах [2:0]
    
    // 6.3. Выбор канала 0 (PA0 = ADC1_IN0)
    ADC1->CHSELR = (1UL << 0);               // CHSEL0 = 1
    
    // 6.4. Режим работы: одиночное преобразование, 12 бит (по умолчанию)
    ADC1->CFGR1 = 0;
    
    /* 7. Включение ADC */
    ADC1->ISR |= ADC_ISR_ADRDY;              // Сбросить флаг ADRDY
    ADC1->CR  |= ADC_CR_ADEN;                // Включить ADC
    while (!(ADC1->ISR & ADC_ISR_ADRDY)) { __NOP(); }  // Дождаться готовности
}

/**
 * @brief Выполнить одиночное преобразование
 * @return 12-битное значение (0-4095)
 */
uint16_t ADC1_ReadOnce(void)
{
    // Запуск преобразования
    ADC1->CR |= ADC_CR_ADSTART;
    
    // Ожидание окончания
    while (!(ADC1->ISR & ADC_ISR_EOC)) { __NOP(); }
    
    // Чтение результата (12 бит)
    return (uint16_t)(ADC1->DR & 0x0FFFU);
}

/**
 * @brief Чтение указанного канала
 * @param channel Номер канала (0-15)
 * @return Значение ADC
 */
uint16_t ADC1_ReadChannel(uint8_t channel)
{
    if (channel > 15) return 0;
    
    // Выбор канала
    ADC1->CHSELR = (1UL << channel);
    __NOP(); __NOP();                         // Задержка установки канала
    
    // Запуск и ожидание
    ADC1->CR |= ADC_CR_ADSTART;
    while (!(ADC1->ISR & ADC_ISR_EOC)) { __NOP(); }
    
    return (uint16_t)(ADC1->DR & 0x0FFFU);
}

/**
 * @brief Конвертация значения ADC в милливольты
 * @param adc_value Значение ADC (0-4095)
 * @param vref_mv Опорное напряжение в мВ (обычно 3300)
 * @return Напряжение в мВ
 */
uint32_t ADC_ToVoltage_mV(uint16_t adc_value, uint32_t vref_mv)
{
    return ((uint32_t)adc_value * vref_mv) / 4095U;
}

/* Пример использования:
int main(void)
{
    SystemInit();  // Инициализация системы (если нужно)
    
    ADC1_Init_Single_PA0();
    
    while (1)
    {
        uint16_t raw = ADC1_ReadOnce();
        uint32_t mv = ADC_ToVoltage_mV(raw, 3300);
        
        // Использование значения...
        
        // Задержка
        for (volatile uint32_t i = 0; i < 100000; i++) { __NOP(); }
    }
}
*/
