#include "mip_display.hpp"


MipDisplay::MipDisplay(int spi_clock) {

  pigpio = pigpio_start(0, 0);
  spi = spi_open(pigpio, 0, spi_clock, 0);
  usleep(6);

  set_mode(pigpio, GPIO_DISP, PI_OUTPUT);
  set_mode(pigpio, GPIO_SCS, PI_OUTPUT);
  set_mode(pigpio, GPIO_VCOMSEL, PI_OUTPUT);
  set_mode(pigpio, GPIO_BACKLIGHT, PI_OUTPUT);
  usleep(6);

  gpio_write(pigpio, GPIO_SCS, 0);
  gpio_write(pigpio, GPIO_DISP, 1);
  gpio_write(pigpio, GPIO_VCOMSEL, 1);
  usleep(6);

  hardware_PWM(pigpio, GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, 0);
  usleep(6);

  //threads_.emplace((&MipDisplay::draw_worker, this));
  status_quit = false;
  threads_.push_back(std::thread(&MipDisplay::draw_worker, this));
}

MipDisplay::~MipDisplay() {
}

void MipDisplay::quit() {
  {
    std::unique_lock<std::mutex> ul(mutex_);
    status_quit = true;
  } //release lock
  cv_.notify_all();
  for(unsigned int i = 0; i < threads_.size(); i++) {
    threads_.at(i).join();
  }

  set_brightness(0);
  clear();

  gpio_write(pigpio, GPIO_DISP, 0); //OFF
  usleep(100000);
  spi_close(pigpio, spi);
  pigpio_stop(pigpio);

  delete[] buf_image;
  delete[] pre_buf_image;
}

void MipDisplay::set_screen_size(int w, int h) {
  WIDTH = w;
  HEIGHT = h;
  BUF_WIDTH = WIDTH*BPP/8 + 2;
  int length = HEIGHT*BUF_WIDTH;
  
  buf_image = new char[length];
  pre_buf_image = new char[length];

  clear_buf();
  memcpy(pre_buf_image, buf_image, length);
}

void MipDisplay::set_refresh_count(int r) {
  refresh_count = r;
}

void MipDisplay::clear_buf() {
  memset(buf_image, 0, HEIGHT*BUF_WIDTH);
  for(int i = 0; i < HEIGHT; i++) {
    buf_image[i*BUF_WIDTH] = UPDATE_MODE + (i >> 8);
    buf_image[i*BUF_WIDTH+1] = (char)((unsigned int)i);
  }
}

void MipDisplay::clear() {
  gpio_write(pigpio, GPIO_SCS, 1);
  usleep(6);
  spi_write(pigpio, spi, buf_clear, 2);
  gpio_write(pigpio, GPIO_SCS, 0);
  usleep(6);
}

void MipDisplay::no_update() {
  gpio_write(pigpio, GPIO_SCS, 1);
  usleep(6);
  spi_write(pigpio, spi, buf_no_update, 2);
  gpio_write(pigpio, GPIO_SCS, 0);
  usleep(6);
}

void MipDisplay::set_brightness(int brightness) {
  int b = brightness;
  if(b >= 100) {
    b = 100;
  } else if (b <= 0) {
    b = 0;
  }
  hardware_PWM(pigpio, GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, b*10000);
  usleep(50000);
}

void MipDisplay::inversion(float sec) {
  float s = sec;
  bool state = true;
  while(s > 0) {
    gpio_write(pigpio, GPIO_SCS, 1);
    usleep(6);
    if(state) {
      spi_write(pigpio, spi, buf_inversion, 2);
    }
    else {
      spi_write(pigpio, spi, buf_no_update, 2);
    }
    gpio_write(pigpio, GPIO_SCS, 0);
    usleep(inversion_interval*1000000);
    s -= inversion_interval;
    state = !state;
  }
  spi_write(pigpio, spi, buf_no_update, 2);
}

void MipDisplay::draw_worker() {
  while (1) {
    std::vector<char> q;
    {
      std::unique_lock<std::mutex> ul(mutex_);
      while (queue_.empty()) {
        if (get_status_quit()) { return; }
        //if (status_quit) { return; }
        cv_.wait(ul);
      }
      q = queue_.front();
      queue_.pop();
    } //release
    draw(q);
  }
}

bool MipDisplay::get_status_quit() {
  return status_quit;
}

void MipDisplay::update(unsigned char* image) {
  int c_index;
  unsigned int bit_count = 0;
  unsigned char bit_color;
  int update_lines = 0;
  int buf_index = 0;
  clear_buf();

  for(int y = 0; y < HEIGHT; y++) {
    bit_count = 0;
    for(int x = 0; x < WIDTH; x++) {
      for(int c = 0; c < 3; c++) {
        c_index = (y*WIDTH + x)*BPP + c;
        bit_color = image[c_index] / 128;
        //pseudo 3bit color (128~216: simple dithering) 
        if(bit_color and image[c_index] <= 216 and x%2 == y%2) {
          bit_color = 0;
        }

        if(bit_color) {
          buf_image[y*BUF_WIDTH+2+(bit_count/8)] |= (1 << (7-(bit_count%8)));
          //buf_image[y*BUF_WIDTH+2+((bit_count%(WIDTH*3))/8)] |= (1 << 7-(bit_count%8));
        }
        bit_count++;
      }
    }
    buf_index = y*BUF_WIDTH;
    if(memcmp(&buf_image[buf_index], &pre_buf_image[buf_index], BUF_WIDTH) != 0) {
      memcpy(&pre_buf_image[buf_index], &buf_image[buf_index], BUF_WIDTH);
      memcpy(&buf_image[update_lines*BUF_WIDTH], &pre_buf_image[buf_index], BUF_WIDTH);
      update_lines++;  
    }
  }

  //std::cout << "    diff " << int(update_lines*100/HEIGHT) << "%, " << BUF_WIDTH << "*" << update_lines << "=" << BUF_WIDTH*update_lines << std::endl;
  if(update_lines == 0) {
    return;
  }
  if(diff_count == refresh_count) {
    update_lines = HEIGHT;
    diff_count = 0;
  }
  diff_count++;

  {
    std::unique_lock<std::mutex> ul(mutex_);
    if(update_lines < MAX_HEIGHT_PER_ONCE) { 
      queue_.emplace(buf_image, buf_image+BUF_WIDTH*update_lines);
    }
    else {
      int l = BUF_WIDTH*update_lines/2;
      queue_.emplace(buf_image, buf_image+l);
      queue_.emplace(buf_image, &buf_image[l]+l);
    }
  } //release lock
  cv_.notify_all();
}

void MipDisplay::draw(std::vector<char>& buf_queue) {
  //std::chrono::system_clock::time_point start = std::chrono::system_clock::now();
  usleep(10); //0.0001
  gpio_write(pigpio, GPIO_SCS, 1);
  spi_write(pigpio, spi, buf_queue.data(), buf_queue.size());
  spi_write(pigpio, spi, buf_no_update, 2);
  gpio_write(pigpio, GPIO_SCS, 0);
  usleep(10); //0.0001
  //int diff_time = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::system_clock::now()-start).count();
  //std::cout << "###### draw(C)   " <<  (float)diff_time / 1000000 << std::endl;
}

