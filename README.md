
# Event Hubs Proxy #

[Azure Event Hubs service](https://docs.microsoft.com/en-us/azure/event-hubs/event-hubs-what-is-event-hubs) is a robust, scalable, managed solution for event ingestion in the cloud. One of the common scenarios for using Event Hubs is an IoT scenario where many devices send data to the cloud for analysis and storage. Event Hubs has an FQDN endpoint which does not guarantee a static IP address for the service. However, in some uncommon real world scenarios, devices might need to send events to the cloud with a static IP destination (e.g. some on-prem traditional systems require IP whitelisting).

This repository offers a solution for these uncommon scenarios by creating a highly available reverse proxy to event hubs behind a static public IP on Azure.

## Solution Architecture: ##

The solution uses [nginx](http://nginx.org/en/) as a reverse proxy deployed on a VM Scale Set for high availability and the potential for adding autoscaling. The scale set is accessed via a load balancer with a static public IP.

![Diagram](/resources/diagram.png)

## Setup: ##

This section will detail the setup of the load balancer and VMSS. It assumes an Events Hub has already been created (see [this article](https://docs.microsoft.com/en-us/azure/event-hubs/event-hubs-create) for further information on how to create an Events Hub instance).

*STEP 1: Install the Azure CLI*

The rest of this section will make use of the [Azure CLI 2.0](https://docs.microsoft.com/en-us/cli/azure/overview). Since it is a Python application, you can install it on your work station using pip:

```
pip install azure-cli
```

*STEP 2: Create a resource group*

```
az group create -n [RESOURCE-GROUP-NAME] -l [LOCATION]
```

*STEP 3: Create a Public IP*

This IP will be used by the load balancer and will be essentially the proxy IP address

```
az network public-ip create -g [RESOURCE-GROUP-NAME] -n [IP-INSTANCE-NAME] --allocation-method Static
```

If the creation is successful you should get an output with the assigned IP. For Example:

```json
{
    ...
    "ipAddress": "52.178.70.112",
    ...
}
```

*STEP 4: Create a VM image with nginx and installed certificates*

To create a custom image that will include nginx, we'll start with creating a vanilla Ubunutu instance that will be the basis for our image.
Create a simple Ubunutu VM via:

```
az vm create -g [RESOURCE-GROUP-NAME] -n [VM-NAME] --image ubuntuLTS --authentication-type password --admin-username [ADMIN-USERNAME] --admin-password [ADMIN-PASSWORD]
```

SSH into the machine using the SSH command (on Linux) or PuTTY (on Windows) using the VM public IP given as output from the above command and the username/password you entered. 

Install nginx on the new machine:

```
sudo apt-get update
sudo apt-get install nginx
```

We'll be using nginx as a reverse proxy and will want to use HTTPS but since nginx does not support the CONNECT method, we'll need to install certificates on the machine. For the purpose of this guide we'll use a self-signed certificate though normally you would install proper certificates on the machine at this stage.

To create a self signed certificate run on the machine (XXX.XXX.XXX.XXX should be replaced with the Public IP you created earlier):
```
openssl req -new -newkey rsa:2048 -days 365 -nodes -x509 -keyout cert.key -out cert.crt -subj /CN=XXX.XXX.XXX.XXX
```

>Note: Using self-signed certificates should only be done in development or test environments. In a public production environment certificates signed by a known CA should be used.

Copy the certificates to a new location in /etc/nginx:

```
sudo mkdir /etc/nginx/ssl
sudo cp cert.* /etc/nginx/ssl
```

To configure nginx, we'll replace the file `/etc/nginx/sites-available/default` but it is always good practice to first save a backup:

```
cd /etc/nginx/sites-available/
sudo cp default default.bkp
```

As a basis for the new configuration you can use the config file in this repo [`ngnix-proxy-config.txt`](/proxy/ngnix-proxy-config.txt)

```
sudo wget https://raw.githubusercontent.com/orizohar/eventhub-proxy/master/proxy/ngnix-proxy-config.txt
sudo mv ngnix-proxy-config.txt default
```

The file you pull should look like this:

```
server {
        listen 443 ssl;
        # Replace the [PROXY-PUBLIC-IP] with the public IP you created for the proxy. e.g. 13.95.22.45
        server_name [PROXY-PUBLIC-IP];

        ssl_certificate /etc/nginx/ssl/cert.crt;
        ssl_certificate_key /etc/nginx/ssl/cert.key;

        ssl_session_timeout 5m;

        ssl_protocols TLSv1 TLSv1.1 TLSv1.2;
        ssl_session_cache  builtin:1000  shared:SSL:10m;
        ssl_ciphers HIGH:!aNULL:!eNULL:!EXPORT:!CAMELLIA:!DES:!MD5:!PSK:!RC4;
        ssl_prefer_server_ciphers on;

        underscores_in_headers on;
        proxy_pass_request_headers on;

        location / {
                # Replace the [EVENT-HUB-FQDN] with the URL of your event hub. e.g. https://myeventhub001.servicebus.windows.net
                proxy_pass      [EVENT-HUB-FQDN];
                proxy_read_timeout 90;
        }
}

```

Make sure to replace [PROXY-PUBLIC-IP] in line 4 and [EVENT-HUB-FQDN] in line 21 with your values.
You can do this by using nano:

```
sudo nano /etc/nginx/sites-available/default 
```

Also note the nginx config expects the certifcate and key previously created to be located in `/etc/nginx/ssl`.

To verify the correctness of the config file, run the following:

```
sudo nginx -t
```

To apply the change run:

```
sudo service nginx restart
```

At this point the VM is configured (you can test it is working as a proxy using the proxy client in this repo, see below). Now we can go ahead and generalize the VM and create an image to be used by the scale set.

>Note: Generalizing a VM will make it unusable

In an SSH session run the following:

```
sudo waagent -deprovision+user -force
exit
```

In your workstation run:

```
az vm deallocate -g [RESOURCE-GROUP-NAME] -n [VM-NAME]
az vm image create -g [RESOURCE-GROUP-NAME] -n [IMAGE_NAME] --source [VM-NAME]
```

The output of the image creation command should provide the image ID which should look something like this:
```json
{
    ...
    "id": "/subscriptions/[SUBSCRIPTION-GUID]/resourceGroups/[RESOURCE-GROUP-NAME]/providers/Microsoft.Compute/images/[IMAGE-NAME]",
    ...
}
```

*STEP 5: Deploy the VMSS*

Now that an image with a configured nginx reverse proxy is available, the load balancer and scale set can be deployed using the template file in this repo using the below command. Make sure to edit `arm-template/azure-template.params.json` with the resource ID of the public IP created in step 3 and the ID for the custom image created in step 5.

```
az group deployment create -g [RESOURCE-GROUP-NAME] --template-file arm-template/azure-template.json --parameters @arm-template/azure-template.params.json
```

## Proxy Client: ##

This repo includes some Python reference code for sending events to the proxy. Events generated are in JSON format.
The python application proxy expects the following environment variables to be defined in runtime:

- **EH_PROXY_DNS** : IP or DNS of proxy.
- **SB_NAMESPACE** : Service bus namespace for event hub
- **EH_NAME** : Event hub name
- **SB_KEYNAME** : SAS access key name
- **SB_KEYVAL** : SAS access key value

Optionally, if you are using self-signed certificates, you can provide the path to them so the request to the proxy will pass the certificate check:
- **EH_PROXY_CERT_PATH** : Path to the certificate file

(This reference code does not use the Azure event hub SDK because of the use of the proxy)

## Resources: ##

- [nginx](http://nginx.org/)
- [Virtual Machine Scale Sets](https://docs.microsoft.com/en-us/azure/virtual-machine-scale-sets/virtual-machine-scale-sets-overview)
- [Azure Event Hubs](https://docs.microsoft.com/en-us/azure/event-hubs/event-hubs-what-is-event-hubs)
- [Azure CLI 2.0 command reference](https://docs.microsoft.com/en-us/cli/azure/)

