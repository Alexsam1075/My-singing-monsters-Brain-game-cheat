import pygame
import pyautogui
import sys
import time
import threading
from typing import Dict, List
import win32api
import win32con
import win32gui
import pythoncom


class MemoryCheatOverlay:
    def __init__(self) -> None:
        pygame.init()

        # === НАСТРОЙКИ ===
        self.capture_size: int = 180                  # Размер захватываемой области (px)
        self.display_size: int = 160                  # Размер отображаемого квадрата
        self.capture_delay: float = 0.5               # Задержка после клика перед захватом
        self.overlay_transparency: int = 40           # Прозрачность от 0 (невидимый) до 100 (полностью видимый)

        # Разрешение экрана
        info = pygame.display.Info()
        self.screen_width: int = info.current_w
        self.screen_height: int = info.current_h

        # Полноэкранное окно без рамки
        self.screen = pygame.display.set_mode(
            (self.screen_width, self.screen_height),
            pygame.NOFRAME | pygame.SRCALPHA  # SRCALPHA важен для корректной работы альфы
        )
        pygame.display.set_caption("Memory Cheat Overlay")

        # Получаем HWND окна Pygame
        hwnd = pygame.display.get_wm_info()["window"]

        # Настраиваем стили окна
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        new_ex_style = (
            ex_style
            | win32con.WS_EX_LAYERED          # Поддержка прозрачности
            | win32con.WS_EX_TRANSPARENT      # Клик-through (клики проходят сквозь окно)
            | win32con.WS_EX_TOPMOST          # Поверх всех окон
            | win32con.WS_EX_TOOLWINDOW       # Скрыть из Alt+Tab и панели задач
            | win32con.WS_EX_NOACTIVATE       # Не активировать при клике
        )
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, new_ex_style)

        # === ГЛОБАЛЬНАЯ ПОЛУПРОЗРАЧНОСТЬ ===
        # Переводим 0-100 в 0-255
        alpha_value = int((self.overlay_transparency / 100.0) * 255)
        alpha_value = max(0, min(255, alpha_value))  # Защита от выхода за пределы

        win32gui.SetLayeredWindowAttributes(
            hwnd,
            0,              # Не используем color key
            alpha_value,    # Глобальная альфа
            win32con.LWA_ALPHA
        )

        # Фиксируем окно поверх всего
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOPMOST,
            0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
        )

        # Состояние
        self.captures: Dict[tuple[int, int], pygame.Surface] = {}
        self.capture_queue: List[dict] = []
        self.capture_enabled: bool = True
        self.mouse_listener_active: bool = True

        # Запускаем слушатели
        self.start_keyboard_listener()
        self.start_mouse_listener()

        # Главный цикл
        self.run()

    def start_keyboard_listener(self) -> None:
        thread = threading.Thread(target=self.keyboard_listener_thread, daemon=True)
        thread.start()

    def keyboard_listener_thread(self) -> None:
        """K — включить/выключить захват, L — очистить все"""
        try:
            prev_k = win32api.GetKeyState(0x4B)  # VK_K
            prev_l = win32api.GetKeyState(0x4C)  # VK_L

            while self.mouse_listener_active:
                time.sleep(0.01)

                curr_k = win32api.GetKeyState(0x4B)
                if curr_k != prev_k and curr_k < 0:
                    self.capture_enabled = not self.capture_enabled
                    status = "ВКЛЮЧЕНА" if self.capture_enabled else "ВЫКЛЮЧЕНА"
                    print(f"[Overlay] Запись скриншотов: {status}")
                prev_k = curr_k

                curr_l = win32api.GetKeyState(0x4C)
                if curr_l != prev_l and curr_l < 0:
                    self.captures.clear()
                    print("[Overlay] Все скриншоты удалены")
                prev_l = curr_l

        except Exception as e:
            print(f"Ошибка в потоке клавиатуры: {e}")

    def start_mouse_listener(self) -> None:
        thread = threading.Thread(target=self.mouse_listener_thread, daemon=True)
        thread.start()

    def mouse_listener_thread(self) -> None:
        pythoncom.CoInitialize()
        try:
            last_state = win32api.GetKeyState(0x01)  # ЛКМ

            while self.mouse_listener_active:
                current_state = win32api.GetKeyState(0x01)
                if current_state != last_state:
                    if current_state < 0 and self.capture_enabled:  # Нажата ЛКМ
                        x, y = win32api.GetCursorPos()
                        self.capture_queue.append({
                            "pos": (x, y),
                            "scheduled_time": time.time() + self.capture_delay
                        })
                last_state = current_state
                time.sleep(0.01)
        except Exception as e:
            print(f"Ошибка в потоке мыши: {e}")
        finally:
            pythoncom.CoUninitialize()

    def perform_capture(self, pos: tuple[int, int]) -> pygame.Surface | None:
        try:
            x, y = pos
            left = max(0, x - self.capture_size // 2)
            top = max(0, y - self.capture_size // 2)

            screenshot = pyautogui.screenshot(region=(left, top, self.capture_size, self.capture_size))
            pygame_img = pygame.image.fromstring(
                screenshot.tobytes(),
                screenshot.size,
                screenshot.mode
            )

            # Масштабируем до нужного размера
            scaled = pygame.transform.smoothscale(pygame_img, (self.display_size, self.display_size))

            return scaled
        except Exception as e:
            print(f"Ошибка захвата: {e}")
            return None

    def process_queue(self) -> None:
        current_time = time.time()
        for item in self.capture_queue[:]:
            if current_time >= item["scheduled_time"]:
                surf = self.perform_capture(item["pos"])
                if surf:
                    # Округляем позицию до 10 пикселей для предотвращения дубликатов рядом
                    key = (round(item["pos"][0] / 10) * 10, round(item["pos"][1] / 10) * 10)
                    self.captures[key] = surf
                self.capture_queue.remove(item)

    def draw(self) -> None:
        # Прозрачный фон (важно для SRCALPHA)
        self.screen.fill((0, 0, 0, 0))

        for (x, y), surf in self.captures.items():
            dest_x = x - self.display_size // 2
            dest_y = y - self.display_size // 2
            self.screen.blit(surf, (dest_x, dest_y))

    def run(self) -> None:
        clock = pygame.time.Clock()

        print("\n=== Memory Cheat Overlay ===")
        print(f"Текущая прозрачность оверлея: {self.overlay_transparency}% (0–100)")
        print("• ЛКМ → захват скриншота с задержкой 0.5с")
        print("• K → включить/выключить захват")
        print("• L → очистить все скриншоты")
        print("• Клик проходит сквозь оверлей в игру\n")

        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            self.process_queue()
            self.draw()
            pygame.display.flip()
            clock.tick(60)

        self.mouse_listener_active = False
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    MemoryCheatOverlay()