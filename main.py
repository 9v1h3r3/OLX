import time
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException

class E2EEMessengerBot:
    def __init__(self):
        self.driver = None
        self.wait = None
        
    def setup_driver(self):
        """Chrome driver setup with human-like options"""
        print("🔄 Setting up Chrome driver...")
        options = webdriver.ChromeOptions()
        
        # Anti-detection options
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Regular options
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-extensions")
        
        self.driver = webdriver.Chrome(options=options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.wait = WebDriverWait(self.driver, 25)
        self.driver.maximize_window()
        print("✅ Chrome driver setup completed")
    
    def load_config_files(self):
        """Saari configuration files load karein"""
        self.targets = []
        self.messages = []
        self.delays = []
        
        try:
            # target.txt load karein
            with open("target.txt", "r", encoding="utf-8") as f:
                self.targets = [line.strip() for line in f.readlines() if line.strip()]
            print(f"✅ Targets loaded: {len(self.targets)}")
            
            # message.txt load karein
            with open("message.txt", "r", encoding="utf-8") as f:
                self.messages = [line.strip() for line in f.readlines() if line.strip()]
            print(f"✅ Messages loaded: {len(self.messages)}")
            
            # time.txt load karein (multiple delays ke liye)
            with open("time.txt", "r", encoding="utf-8") as f:
                self.delays = [int(line.strip()) for line in f.readlines() if line.strip()]
            if not self.delays:
                self.delays = [10, 15, 20]  # Default delays
            print(f"✅ Delays loaded: {self.delays}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error loading config files: {str(e)}")
            return False
    
    def login_with_session(self):
        """Session cookies use karke login karein"""
        print("\n🔐 Logging in with session...")
        try:
            # Pehle facebook.com pe jayein
            self.driver.get("https://www.facebook.com")
            time.sleep(5)
            
            # Check if already logged in
            if "login" not in self.driver.current_url.lower():
                print("✅ Already logged in")
                return True
            else:
                print("❌ Not logged in. Manual login required.")
                input("⚠️  Please login manually in the browser and press Enter to continue...")
                return True
                
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
            return False
    
    def navigate_to_e2ee_chat(self, target_id):
        """Direct E2EE chat link use karein"""
        print(f"\n💬 Navigating to E2EE chat: {target_id}")
        try:
            chat_url = f"https://www.facebook.com/messages/t/{target_id}"
            self.driver.get(chat_url)
            time.sleep(7)
            
            # Wait for chat to load - E2EE specific indicators
            chat_indicators = [
                "//div[contains(text(), 'end-to-end encrypted')]",
                "//div[contains(@class, 'e2ee')]",
                "//div[@role='textbox']",
                "//div[@contenteditable='true']"
            ]
            
            for indicator in chat_indicators:
                try:
                    self.wait.until(EC.presence_of_element_located((By.XPATH, indicator)))
                    print("✅ E2EE Chat loaded successfully")
                    return True
                except:
                    continue
            
            print("⚠️  E2EE indicators not found, but continuing...")
            return True
            
        except Exception as e:
            print(f"❌ Error navigating to E2EE chat: {str(e)}")
            return False
    
    def find_message_box_e2ee(self):
        """E2EE chat ke message box ko find karein"""
        print("🔍 Finding message box in E2EE chat...")
        
        # Multiple possible selectors for E2EE message box
        message_box_selectors = [
            "//div[@role='textbox' and @contenteditable='true']",
            "//div[@contenteditable='true']",
            "//div[contains(@class, 'notranslate')]",
            "//div[@aria-label='Message']",
            "//p[@contenteditable='true']"
        ]
        
        for selector in message_box_selectors:
            try:
                message_box = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                print(f"✅ Message box found with selector: {selector}")
                return message_box
            except:
                continue
        
        print("❌ Could not find message box")
        return None
    
    def send_message_e2ee(self, target_id, message):
        """E2EE chat mein message send karein"""
        try:
            message_box = self.find_message_box_e2ee()
            if not message_box:
                return False
            
            # Message type karein
            message_box.click()
            time.sleep(2)
            
            # Clear existing text (if any)
            message_box.send_keys(Keys.CONTROL + "a")
            message_box.send_keys(Keys.BACKSPACE)
            time.sleep(1)
            
            # Type message character by character (human-like)
            for char in message:
                message_box.send_keys(char)
                time.sleep(random.uniform(0.05, 0.1))
            
            time.sleep(2)
            
            # Send message using Enter key
            message_box.send_keys(Keys.ENTER)
            print(f"✅ Message sent to {target_id}")
            
            # Send ke baad thoda wait karein
            time.sleep(3)
            return True
            
        except Exception as e:
            print(f"❌ Error sending message to {target_id}: {str(e)}")
            return False
    
    def process_all_targets(self):
        """Saare targets ko process karein"""
        print(f"\n🚀 Starting E2EE messaging for {len(self.targets)} targets...")
        
        successful = 0
        failed_targets = []
        
        for i, target in enumerate(self.targets, 1):
            print(f"\n{'='*50}")
            print(f"Processing {i}/{len(self.targets)}: {target}")
            print(f"{'='*50}")
            
            # E2EE chat navigate karein
            if self.navigate_to_e2ee_chat(target):
                # Random message select karein
                message = random.choice(self.messages) if self.messages else "Hello from automated system"
                
                # Message send karein
                if self.send_message_e2ee(target, message):
                    successful += 1
                    print(f"✅ SUCCESS: {target}")
                else:
                    failed_targets.append(target)
                    print(f"❌ FAILED: {target}")
            else:
                failed_targets.append(target)
                print(f"❌ FAILED to access: {target}")
            
            # Random delay between messages
            if i < len(self.targets):
                delay = random.choice(self.delays)
                print(f"⏳ Waiting {delay} seconds...")
                time.sleep(delay)
        
        # Summary show karein
        self.show_summary(successful, failed_targets)
        return successful
    
    def show_summary(self, successful, failed_targets):
        """Final results show karein"""
        print(f"\n{'='*60}")
        print("📊 E2EE MESSAGING SUMMARY")
        print(f"{'='*60}")
        print(f"✅ Successful: {successful}/{len(self.targets)}")
        print(f"❌ Failed: {len(failed_targets)}/{len(self.targets)}")
        
        if failed_targets:
            print(f"📋 Failed targets: {failed_targets}")
    
    def run(self):
        """Main execution function"""
        print("🚀 E2EE Facebook Messenger Bot Starting...")
        
        # Configuration load karein
        if not self.load_config_files():
            return
        
        # Driver setup karein
        self.setup_driver()
        
        try:
            # Login karein
            if not self.login_with_session():
                return
            
            # Messaging process start karein
            successful = self.process_all_targets()
            
            if successful > 0:
                print(f"\n🎉 Successfully sent {successful} E2EE messages!")
            else:
                print(f"\n😞 No E2EE messages were sent successfully.")
            
        except Exception as e:
            print(f"❌ Unexpected error: {str(e)}")
        
        finally:
            # Browser close karein
            if self.driver:
                input("\nPress Enter to close browser...")
                self.driver.quit()
                print("✅ Browser closed.")

# Run the bot
if __name__ == "__main__":
    bot = E2EEMessengerBot()
    bot.run()
