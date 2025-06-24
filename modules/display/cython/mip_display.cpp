#include "mip_display.hpp"


MipDisplay::MipDisplay(int spi_clock, int pcb_pattern) {

  // pcb_pattern
  //   0: None, 1: SWITCH_SCIENCE_MIP_BOARD, 2: PIZERO_BIKECOMPUTER

  pigpio = pigpio_start(0, 0);
#ifdef NO_USE_SPI_CE0
  spi = spi_open(pigpio, 0, spi_clock, 0b00100000);
#else
  spi = spi_open(pigpio, 0, spi_clock, 0b00000100);
#endif
  usleep(6);

#ifdef NO_USE_SPI_CE0
  set_mode(pigpio, GPIO_SCS, PI_OUTPUT);
#endif
  set_mode(pigpio, GPIO_DISP, PI_OUTPUT);
  set_mode(pigpio, GPIO_VCOMSEL, PI_OUTPUT);
  set_mode(pigpio, GPIO_BACKLIGHT, PI_OUTPUT);
  if (pcb_pattern == 1){
    set_PWM = &MipDisplay::set_PWM_switch_science_mip_board;
  }
  else if(pcb_pattern == 2) {
    set_PWM = &MipDisplay::set_PWM_pizero_bikecomputer_pcb;
    set_mode(pigpio, GPIO_BACKLIGHT_SWITCH, PI_OUTPUT);
  }
  usleep(6);

#ifdef NO_USE_SPI_CE0
  gpio_write(pigpio, GPIO_SCS, 0);
#endif
  gpio_write(pigpio, GPIO_DISP, 1);
  gpio_write(pigpio, GPIO_VCOMSEL, 1);
  usleep(6);

  set_brightness(0);
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

void MipDisplay::set_screen_size(int w, int h, int c) {
  WIDTH = w;
  HEIGHT = h;
  COLORS = c;

  if(COLORS == 2) {
    BPP = 1;
    BUF_WIDTH = WIDTH*BPP/8 + 2;
    conv_color = &MipDisplay::conv_1bit_color;
  }
  else if(COLORS == 8) {
    BPP = 3;
    BUF_WIDTH = WIDTH*BPP/8 + 2;
    conv_color = &MipDisplay::conv_3bit_color;
  }
  else if(COLORS == 64) {
    BPP = 6;
    BUF_WIDTH = WIDTH*BPP/8 + 4;
    HALF_BUF_WIDTH_64COLORS = WIDTH*BPP/8/2;
    conv_color = &MipDisplay::conv_4bit_color;
  }
  int length = HEIGHT*BUF_WIDTH;
  
  buf_image = new char[length];
  pre_buf_image = new char[length];

  SPI_MAX_ROWS = int(SPI_MAX_BUF_SIZE/BUF_WIDTH);

  clear_buf();
  memcpy(pre_buf_image, buf_image, length);
}

void MipDisplay::clear_buf() {
  memset(buf_image, 0, HEIGHT*BUF_WIDTH);
  for(int i = 0; i < HEIGHT; i++) {
    buf_image[i*BUF_WIDTH] = UPDATE_MODE + (i >> 8);
    buf_image[i*BUF_WIDTH+1] = (char)((unsigned int)i);

/*
 * The following code is adapted from an Apache License 2.0 project.
 * Copyright (c) Azumo 2024
 * 
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *     third-party/apache/LICENSE.Apache2
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 * 
 * start
 */
    if(COLORS == 64) {
      buf_image[i*BUF_WIDTH] |= 0b10;
      buf_image[i*BUF_WIDTH+2+HALF_BUF_WIDTH_64COLORS] = (i >> 8);
      buf_image[i*BUF_WIDTH+2+HALF_BUF_WIDTH_64COLORS+1] = (char)((unsigned int)i);
    }
  /* end */
  }
}

void MipDisplay::clear() {
#ifdef NO_USE_SPI_CE0
  gpio_write(pigpio, GPIO_SCS, 1);
  usleep(6);
#endif
  spi_write(pigpio, spi, buf_clear, 2);
#ifdef NO_USE_SPI_CE0
  gpio_write(pigpio, GPIO_SCS, 0);
  usleep(6);
#endif
}

void MipDisplay::no_update() {
#ifdef NO_USE_SPI_CE0
  gpio_write(pigpio, GPIO_SCS, 1);
  usleep(6);
#endif
  spi_write(pigpio, spi, buf_no_update, 2);
#ifdef NO_USE_SPI_CE0
  gpio_write(pigpio, GPIO_SCS, 0);
  usleep(6);
#endif
}

void MipDisplay::set_PWM_switch_science_mip_board(int b) {
  hardware_PWM(pigpio, GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, b*10000);
}

void MipDisplay::set_PWM_pizero_bikecomputer_pcb(int b) {
  if(b == 0) {
    gpio_write(pigpio, GPIO_BACKLIGHT_SWITCH, 0);
  } else {
    gpio_write(pigpio, GPIO_BACKLIGHT_SWITCH, 1);
  }
  hardware_PWM(pigpio, GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, (100-b)*10000);
}

void MipDisplay::set_brightness(int brightness) {
  if(pre_brightness == brightness) {
    return;
  }

  int b = brightness;
  if(b >= 100) {
    b = 100;
  } else if (b <= 0) {
    b = 0;
  }
  (this->*set_PWM)(b);
  pre_brightness = b;
  usleep(50000);
}

void MipDisplay::inversion(float sec) {
  float s = sec;
  bool state = true;

  while(s > 0) {
#ifdef NO_USE_SPI_CE0
    gpio_write(pigpio, GPIO_SCS, 1);
    usleep(6);
#endif
    if(state) {
      spi_write(pigpio, spi, buf_inversion, 2);
    }
    else {
      spi_write(pigpio, spi, buf_no_update, 2);
    }
#ifdef NO_USE_SPI_CE0
    gpio_write(pigpio, GPIO_SCS, 0);
#endif
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

  int l, l2;
  clear_buf();
  //std::chrono::system_clock::time_point start = std::chrono::system_clock::now();
  int update_lines = (this->*conv_color)(image);
  //int diff_time = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::system_clock::now()-start).count();
  //std::cout << "###### conv_color(C)   " <<  (float)diff_time / 1000000 << std::endl;
  
  //std::cout << "    diff " << int(update_lines*100/HEIGHT) << "%, " << BUF_WIDTH << "*" << update_lines << "=" << BUF_WIDTH*update_lines << std::endl;
  if(update_lines == 0) {
    return;
  }

  {
    std::unique_lock<std::mutex> ul(mutex_);
    if(update_lines < SPI_MAX_ROWS) { 
      l = BUF_WIDTH * update_lines;
      std::vector<char> buf(l + 2);
      memcpy(buf.data(), buf_image, l);
      buf[l] = 0;
      buf[l + 1] = 0;
      queue_.emplace(std::move(buf));
    }
    else {
      l = BUF_WIDTH * int(update_lines/2);
      l2 = BUF_WIDTH*update_lines - l;
      std::vector<char> buf1(l + 2), buf2(l2 + 2);
      memcpy(buf1.data(), buf_image, l);
      memcpy(buf2.data(), buf_image+l, l2);
      buf1[l] = 0;
      buf1[l + 1] = 0;
      buf2[l2] = 0;
      buf2[l2 + 1] = 0;
      queue_.emplace(std::move(buf1));
      queue_.emplace(std::move(buf2));
    }
  } //release lock
  cv_.notify_all();
}

int MipDisplay::conv_1bit_color(unsigned char* image) {
  int update_lines = 0;
  /*
  char *buf_image_diff_index = buf_image;
  char *pre_buf_image_diff_index = pre_buf_image;
  char *buf_image_update_index = buf_image;

  unsigned char *image_index = image;
  char *buf_image_index = buf_image;
  */

  return update_lines;
}

int MipDisplay::conv_2bit_color(unsigned char* image) {

  unsigned char *image_index = image;
  char *buf_image_index = buf_image;

  char *buf_image_diff_index = buf_image;
  char *pre_buf_image_diff_index = pre_buf_image;
  char *buf_image_update_index = buf_image;
  int update_lines = 0;

  int width_24byte = int(WIDTH*3/24);

  for(int y = 0; y < HEIGHT; y++) {
    buf_image_index += 2;
    for(int x = 0; x < width_24byte; x++) {
      *buf_image_index++ = ((*image_index++ >> 7) << 7) | ((*image_index++ >> 7) << 6) | ((*image_index++ >> 7) << 5) | ((*image_index++ >> 7) << 4) | ((*image_index++ >> 7) << 3) | ((*image_index++ >> 7) << 2)  | ((*image_index++ >> 7) << 1) | (*image_index++ >> 7);
      *buf_image_index++ = ((*image_index++ >> 7) << 7) | ((*image_index++ >> 7) << 6) | ((*image_index++ >> 7) << 5) | ((*image_index++ >> 7) << 4) | ((*image_index++ >> 7) << 3) | ((*image_index++ >> 7) << 2)  | ((*image_index++ >> 7) << 1) | (*image_index++ >> 7);
      *buf_image_index++ = ((*image_index++ >> 7) << 7) | ((*image_index++ >> 7) << 6) | ((*image_index++ >> 7) << 5) | ((*image_index++ >> 7) << 4) | ((*image_index++ >> 7) << 3) | ((*image_index++ >> 7) << 2)  | ((*image_index++ >> 7) << 1) | (*image_index++ >> 7);
    }

    if(memcmp(buf_image_diff_index, pre_buf_image_diff_index, BUF_WIDTH) != 0) {
      memcpy(pre_buf_image_diff_index, buf_image_diff_index, BUF_WIDTH);
      memcpy(buf_image_update_index, pre_buf_image_diff_index, BUF_WIDTH);
      update_lines++;
      buf_image_update_index += BUF_WIDTH;
    }
    buf_image_diff_index += BUF_WIDTH;
    pre_buf_image_diff_index += BUF_WIDTH;
  }
  return update_lines;
}

int MipDisplay::conv_3bit_color(unsigned char* image) {

  unsigned char *image_index = image;
  char *buf_image_index = buf_image;

  char *buf_image_diff_index = buf_image;
  char *pre_buf_image_diff_index = pre_buf_image;
  char *buf_image_update_index = buf_image;
  int update_lines = 0;

  bool t_index = true;
  int bit_count;

  for(int y = 0; y < HEIGHT; y++) {
    buf_image_index += 2;
    bit_count = 0;
    
    //3bit color CPU code
    for(int x = 0; x < WIDTH; x++) {
      if(*image_index++ >= thresholds[t_index]) {
        *buf_image_index |= add_bit[bit_count];
      }
      bit_count = (bit_count+1)&7;
      buf_image_index += 1 - (bool)bit_count;

      if(*image_index++ >= thresholds[t_index]) {
        *buf_image_index |= add_bit[bit_count];
      }
      bit_count = (bit_count+1)&7;
      buf_image_index += 1 - (bool)bit_count;

      if(*image_index++ >= thresholds[t_index]) {
        *buf_image_index |= add_bit[bit_count];
      }
      bit_count = (bit_count+1)&7;
      buf_image_index += 1 - (bool)bit_count;

      t_index = !t_index;
    }
    t_index = !t_index;
    
    if(memcmp(buf_image_diff_index, pre_buf_image_diff_index, BUF_WIDTH) != 0) {
      memcpy(pre_buf_image_diff_index, buf_image_diff_index, BUF_WIDTH);
      memcpy(buf_image_update_index, pre_buf_image_diff_index, BUF_WIDTH);
      update_lines++;
      buf_image_update_index += BUF_WIDTH;
    }
    buf_image_diff_index += BUF_WIDTH;
    pre_buf_image_diff_index += BUF_WIDTH;
  }
  return update_lines;
}

/*
 * The following function is adapted from an Apache License 2.0 project.
 * Copyright (c) Azumo 2024
 * 
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *     third-party/apache/LICENSE.Apache2
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
int MipDisplay::conv_4bit_color(unsigned char* image) {
  unsigned char *image_index = image;
  char *buf_image_index = buf_image;
  char *buf_image_index_high = buf_image;

  char *buf_image_diff_index = buf_image;
  char *pre_buf_image_diff_index = pre_buf_image;
  char *buf_image_update_index = buf_image;
  int update_lines = 0;

  int width_24byte = int(WIDTH*3/24);

  buf_image_index += 2;      
  buf_image_index_high += 2 + HALF_BUF_WIDTH_64COLORS + 2;
  for(int y = 0; y < HEIGHT; y++) {
    for(int x = 0; x < width_24byte; x++) {
      *buf_image_index++ = ((*image_index++ & 0b01000000) << 1) | (*image_index++ & 0b01000000) | ((*image_index++ & 0b01000000) >> 1) | ((*image_index++ & 0b01000000) >> 2) | ((*image_index++ & 0b01000000) >> 3) | ((*image_index++& 0b01000000) >> 4)  | ((*image_index++ & 0b01000000) >> 5) | ((*image_index++ & 0b01000000) >> 6);
      *buf_image_index++ = ((*image_index++ & 0b01000000) << 1) | (*image_index++ & 0b01000000) | ((*image_index++ & 0b01000000) >> 1) | ((*image_index++ & 0b01000000) >> 2) | ((*image_index++ & 0b01000000) >> 3) | ((*image_index++& 0b01000000) >> 4)  | ((*image_index++ & 0b01000000) >> 5) | ((*image_index++ & 0b01000000) >> 6);
      *buf_image_index++ = ((*image_index++ & 0b01000000) << 1) | (*image_index++ & 0b01000000) | ((*image_index++ & 0b01000000) >> 1) | ((*image_index++ & 0b01000000) >> 2) | ((*image_index++ & 0b01000000) >> 3) | ((*image_index++& 0b01000000) >> 4)  | ((*image_index++ & 0b01000000) >> 5) | ((*image_index++ & 0b01000000) >> 6);
      image_index -= 24;
      *buf_image_index_high++ = (*image_index++ & 0b10000000) | ((*image_index++ & 0b10000000) >> 1) | ((*image_index++ & 0b10000000) >> 2) | ((*image_index++ & 0b10000000) >> 3) | ((*image_index++ & 0b10000000) >> 4) | ((*image_index++& 0b10000000) >> 5)  | ((*image_index++ & 0b10000000) >> 6) | ((*image_index++ & 0b10000000) >> 7);
      *buf_image_index_high++ = (*image_index++ & 0b10000000) | ((*image_index++ & 0b10000000) >> 1) | ((*image_index++ & 0b10000000) >> 2) | ((*image_index++ & 0b10000000) >> 3) | ((*image_index++ & 0b10000000) >> 4) | ((*image_index++& 0b10000000) >> 5)  | ((*image_index++ & 0b10000000) >> 6) | ((*image_index++ & 0b10000000) >> 7);
      *buf_image_index_high++ = (*image_index++ & 0b10000000) | ((*image_index++ & 0b10000000) >> 1) | ((*image_index++ & 0b10000000) >> 2) | ((*image_index++ & 0b10000000) >> 3) | ((*image_index++ & 0b10000000) >> 4) | ((*image_index++& 0b10000000) >> 5)  | ((*image_index++ & 0b10000000) >> 6) | ((*image_index++ & 0b10000000) >> 7);
    }
    // next start
    buf_image_index += 2 + HALF_BUF_WIDTH_64COLORS + 2;
    buf_image_index_high += 2 + HALF_BUF_WIDTH_64COLORS + 2;
    
    if(memcmp(buf_image_diff_index, pre_buf_image_diff_index, BUF_WIDTH) != 0) {
      memcpy(pre_buf_image_diff_index, buf_image_diff_index, BUF_WIDTH);
      memcpy(buf_image_update_index, pre_buf_image_diff_index, BUF_WIDTH);
      update_lines++;
      buf_image_update_index += BUF_WIDTH;
    }
    buf_image_diff_index += BUF_WIDTH;
    pre_buf_image_diff_index += BUF_WIDTH;
  }
  return update_lines;
}

void MipDisplay::draw(std::vector<char>& buf_queue) {
  //std::chrono::system_clock::time_point start = std::chrono::system_clock::now();
#ifdef NO_USE_SPI_CE0
  usleep(6); //0.00006
  gpio_write(pigpio, GPIO_SCS, 1);
#endif
  spi_write(pigpio, spi, buf_queue.data(), buf_queue.size());
  //spi_write(pigpio, spi, buf_no_update, 2);
#ifdef NO_USE_SPI_CE0
  gpio_write(pigpio, GPIO_SCS, 0);
  usleep(6); //0.00006
#endif
  //int diff_time = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::system_clock::now()-start).count();
  //std::cout << "###### draw(C)   " <<  (float)diff_time / 1000000 << std::endl;
}

