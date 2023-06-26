[Back to software_installation.md](software_installation.md)

# Table of Contents

- [About Live Track](#about-live-track)
- [Create an account](#create-an-account)
- [Create a device](#create-a-device)
- [Import dashboards](#import-dashboards)
- [Connect the device to the dashboard](#connect-the-device-to-the-dashboard)
- [Check the dashboard](#check-the-dashboard)
- [Make the dashboard public](#make-the-dashboard-public)
- [Option](#option)

This document describes the setup of ThingsBoard.  

# About Live Track

[ThingsBoard](https://thingsboard.io) is an open source dashboard platform. It is free to use and is one of the few platforms that can display tracks and paths (used as routes) on a map.

The dashboard can be viewed from the web([Live Demo server](https://demo.thingsboard.io)) and from the application.

- [Google Store](https://play.google.com/store/apps/details?id=org.thingsboard.demo.app)
- [App Store](https://apps.apple.com/us/app/thingsboard-live/id1594355695)

For more details, see [ThingsBoard Documentation](https://thingsboard.io/docs/) and [Getting Started with ThingsBoard](https://thingsboard.io/docs/getting-started-guides/helloworld/).

## dashboards

Three types of dashboards are currently provided.

### [Mobile (map with tracks)](../dashboards/pizero_bikecomputer_w_track_.json)
![Screenshot_20230618-095206](https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/c3df419f-4392-4d83-96ab-1f15508b3605)

### [Mobile (map with routes)](../dashboards/pizero_bikecomputer_w_course_.json)

![Screenshot_20230624-071451](https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/1750bb4d-4d93-4712-aa84-ab99e6b32159)

### [PC desktop (map with tracks)](../dashboards/pizero_bikecomputer_browser_.json)
![Screenshot_20230104-080601~2](https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/e4dfeab8-35a8-4a0c-b6cc-d77df87e86a8)

# Create an account

Go to [ThingsBoard](https://thingsboard.io) and create a free account with "[Live Demo](https://demo.thingsboard.io/signup)" of Community Edition.

# Create a device

Login to Live Demo server([demo.thingsboard.io](demo.thingsboard.io)).
 
Click "Entities" > "Devices" in the menu.
 
<img width="482" alt="thingsboard-01-02-devices" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/80b74243-a0a2-4b86-83b3-a96a9f642581">
 
Click "+" > "Add new device"
 
<img width="830" alt="thingsboard-03-01-add_device" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/248836db-3237-4d84-83e3-347d5dc19b58">
 
Input "Pizero Bikecomputer" in "Name" field and click "Add".

<img width="668" alt="thingsboard-03-02-add_device" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/bcb9dd83-2c50-4816-83ad-c83235acd33a">
 
Now, the device is added. Click this.

<img width="830" alt="thingsboard-03-03-added_device" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/cc155b5a-58d7-40a9-8b3e-cefc66a12501">
 
Click "Copy access token" and paste [THINGSBOARD_API section](./software_installation.md#thingsboard_api-section) of setting.conf.
 
<img width="511" alt="thingsboard-03-04-get_token" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/2f400443-6d79-4c1e-bf90-8513df05965c">


# Import dashboards

Upload the [dashboards](#dashboards) provided.
 
Click "Dashboards" in the menu.
 
<img width="642" alt="thingsboard-01-01-dashboard" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/54840e7d-3663-4d7e-8c85-2d968e4d1718">
 
Click "+" > "Import dashboard". For example, upload ["pizero_bikecomputer_w_track_.json"](../dashboards/pizero_bikecomputer_w_track_.json).
 
<img width="828" alt="thingsboard-02-01-empty" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/f8ac2e19-847b-4e63-9638-19c2bab9a608">
 
Now, the dashboard is added. Click this.
 
<img width="828" alt="thingsboard-02-02-imported" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/47d96960-e8a9-43e3-816f-69fceace2950">

# Connect the device to the dashboard

Allow the imported dashboard to retrieve values for the device you just created.
 
Click edit button.
 
<img width="828" alt="thingsboard-02-03-dashboard" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/13872cf0-9880-4e78-9c1e-2fd13f5e4bd6">
 
Click "Entity aliases" button.
 
<img width="828" alt="thingsboard-02-04-click_entity" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/4b83d314-7d38-49f1-947e-b2c5602db461">
 
Click edit button.
 
<img width="600" alt="thingsboard-03-05-set_device" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/19c29f21-9377-4fee-ae6f-7266ed40e69a">
 
Click "Device" to see the devices created. Select this and save.
 
<img width="522" alt="thingsboard-03-06-set_device" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/3eff7763-0453-400e-8d5c-8ce6238985e8">
 
Click "Save" button.
 
<img width="600" alt="thingsboard-03-07-save_device" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/c8cdad9a-0491-4b0a-ae97-51eaf277c85c">
 
Click check button to save. 
 
<img width="638" alt="thingsboard-03-08-save_dashboard" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/09325e0f-9703-47d0-a7de-131fb8b8fb28">

# Check the dashboard

Now you have the dashboard which works with the program. Check to see if the dashboard works. Run the program in demo mode.

```
$ python3 pizero_bikecomputer.py --demo
```

First, make sure that the value of Power, HR(heartrate) or Speed is available(not 0 or NaN). If you don't see any values, [disable ANT+ in setting.conf](./software_installation.md#ant-section).
 
Then click start button.
 
<img width="400" alt="demo-01" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/27f8a8fa-37d9-4080-b58d-55924d9c63ac">
 
Turn on Live Track from the menu.
 
<img width="400" alt="livetrack-on" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/7f5e190b-138e-4f16-ae4d-3fd0a7c713e0">
 
Open "Devices" section in "Entities" menu. The state of your device changed to "Active". Click it.
 
<img width="750" alt="thingsboard-04-01-device_is_active" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/8a463e9e-4e0d-4642-a635-d837b97d60c4">
 
Click "Latest telemetry" tab. Values sent from the program are displayed.
 
<img width="500" alt="thingsboard-04-02-device_is_active" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/7c7d8fff-ab73-454c-ada5-52808c8eb154">
 
Also, graph values(heartrate/power) are displayed.
 
<img width="600" alt="thingsboard-04-03-device_is_active" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/d5db6dd5-2d81-42c2-bdbd-09bd4299df0b">


# Make the dashboard public

To allow others to see your dashboard, publish your device and dashboard.
 
Click submenu button and "Make device public" from "Devices" menu.

<img width="750" alt="thingsboard-05-01-public_device" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/65809bcb-c9ac-479e-b909-8853a05504bf">
 
Click "Yes".
  
<img width="570" alt="thingsboard-05-02-public_device" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/378fc791-288c-4282-a453-a7f63513a4eb">
 
Then, click submenu button and "Make dashboard public" from "Dashboards" menu.

<img width="750" alt="thingsboard-05-03-public_dashboard" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/3ed55e70-4928-4694-b5ee-53d173aa6b43">
 
You can get the public URL. Click "OK".
 
<img width="650" alt="thingsboard-05-04-public_dashboard" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/063de73e-513b-4a6b-910f-7315355099cb">

If you want to make it private again, do the reverse operation.

# Option

## Change default location in the map

The default location is Tokyo in Japan. If you want to change it, edit your dashboard.

<img width="828" alt="thingsboard-02-03-dashboard" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/13872cf0-9880-4e78-9c1e-2fd13f5e4bd6">

Then click edit button in the map widget.

<img width="627" alt="thingsboard-06-01-change_default_location" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/0ce63d78-6493-4e32-8b3e-c369c3b66d05">

Click "Advanced" tab and "Advanced settings" under "Common map settings".

<img width="549" alt="thingsboard-06-02-change_default_location" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/d68a03ba-007b-4791-9dd6-ce7c8ba48029">

Change the value of "Default map center position". The format is "latitude,longitude".

<img width="540" alt="thingsboard-06-03-change_default_location" src="https://github.com/hishizuka/pizero_bikecomputer/assets/12926652/ec09b780-c24f-4940-823a-0c51008a22c6">


[Back to software_installation.md](software_installation.md)