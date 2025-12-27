# Kubernetes Manifest

This is a basic Kubernetes manifest one can use to deploy Journiv into Kubernetes.

The Ingress has been separated out as not all clusters do ingress the same way.

## Things to change in manifest.yaml

The manifest has a few assumed defaults that you should change first.

### Storage Class in PVC

You should use whatever storage class is appropriate to your cluster.  Most clusters, by default, have "local-path" (using space on the nodes).  This is the default set there:

```
storageClassName: local-path
```

You can use `kubectl get sc` to get your current storage classes, e.g.
```
$ kubectl get sc
NAME                   PROVISIONER             RECLAIMPOLICY   VOLUMEBINDINGMODE      ALLOWVOLUMEEXPANSION   AGE
local-path (default)   rancher.io/local-path   Delete          WaitForFirstConsumer   false                  665d
managed-nfs-storage    fuseim.pri/ifs          Delete          Immediate              true                   665d
```

### Secretkey, Hostname and Protocol

In the `env` block of the Deployment object, we set the env vars Journiv expects.

In the file we see:
```yaml
    - name: SECRET_KEY
        value: "mylongsecretkeyyoushouldchange"
    - name: DOMAIN_NAME
        value: "journiv.example.com"
    - name: DOMAIN_SCHEME
        value: "https"
```

Change the Secret Key to something sufficiently long.  In this example, Journiv expects to be served on "https://journiv.example.com".  This should match your ingress

## Things to change in ingress.yaml

The Ingress is what your Ingress controller will use to route traffic.  In this example we are using the common NGinx Ingress controller.

You can change that, of course, with the annotation:
```
    kubernetes.io/ingress.class: nginx
```

or use 
```
spec:
  ingressClassName: nginx
```

You can see the names your cluster uses with `kubectl get ingressclass`

For example,
```
$ kubectl get ingressclass
NAME    CONTROLLER                     PARAMETERS   AGE
nginx   nginx.org/ingress-controller   <none>       665d
```

This Ingress definition assumes one is using a Cluster Issuer (cert manager).  The "cluster-issuer" annotation should match your cluster issuer:

```
cert-manager.io/cluster-issuer: azuredns-tpkpw
```

Here is an example of cluster issuers
```
 kubectl get clusterissuer
NAME                     READY   AGE
azuredns-tpkpw           True    663d
gcp-le-prod              True    522d
gcpleprod2               True    522d
ionos-cloud-issuer       True    194d
letsencrypt-ionos-prod   True    194d
letsencrypt-prod         True    665d
```

The following lines in the annotation help make sure we redirect "http" to "https" if the user accidentally types "http"

```
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    ingress.kubernetes.io/ssl-redirect: "true"
```

Lastly, there is the "host" FQDN you will want to change that is set in two places:
```
spec:
  rules:
    - host: journiv.example.com
```

and
```
  tls:
    - hosts:
        - journiv.example.com
```

If you remove the TLS steps (if only doing http), you can remove the whole tls block as well as the ssl redirects in the annotations.

# Install

The cluster issuer, if using TLS, will assume you have an A Record already set to your ingress external IP.


## Example A Record setting

Let us assume we are setting "journiv.example.com" to the external IP "75.72.233.202".

### Azure

If one was using Azure, that might be accomplished with 
```
$ az network dns record-set a add-record -g myresourcegroup -z example.com -a 75.72.233.202 -n journiv
```

### GCP 

Google's CloudDNS might use
```
$ gcloud dns record-sets update journivv --rrdatas=75.72.233.202 --type=A --ttl=300 --zone="mydnszone" --project=mygcpproject
```

### AWS 
And AWS might use
```
$ aws route53 change-resource-record-sets --hosted-zone-id ASDFASDFASDF --change-batch file://r53-journiv.json
```

with a JSON block
```
$ cat r53-journiv.json
{
  "Comment": "CREATE journiv A record",
  "Changes": [
    {
      "Action": "CREATE",
      "ResourceRecordSet": {
        "Name": "journiv.example.com",
        "Type": "A",
        "TTL": 300,
        "ResourceRecords": [
          {
            "Value": "75.72.233.202"
          }
        ]
      }
    }
  ]
}
```

### Others

You can use your DNS providers we portal to do similar. You just need to make sure the record is of type "A" and set to your IP

## Applying the YAML in Kubernetes

Now assuming the A Record is set, we can apply first the manifest.yaml:
```
$ kubectl apply -f ./kubernetes.yaml
persistentvolumeclaim/journiv-data-pvc created
deployment.apps/journiv-deployment created
service/journiv-service created
```

Then the ingress
```
$ kubectl apply -f ./ingress.yaml
ingress.networking.k8s.io/journiv-ingress created
Warning: annotation "kubernetes.io/ingress.class" is deprecated, please use 'spec.ingressClassName' instead
```

because the Cert Manager often has to negotiate with Lets Encrypt, it is best to check for the cert to change from "READY: False" to "READY: True"

```
$ kubectl get cert journiv-tls
NAME          READY   SECRET        AGE
journiv-tls   True    journiv-tls   45s
```

We can check that the pod(s) are running:
```
$ kubectl get po -l app=journiv
NAME                                  READY   STATUS    RESTARTS   AGE
journiv-deployment-58b8b7df7c-f9njg   1/1     Running   0          5d
```

That the PVC is created and bound
```
$ kubectl get pvc journiv-data-pvc
NAME               STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS   VOLUMEATTRIBUTESCLASS   AGE
journiv-data-pvc   Bound    pvc-8434a3d9-239d-4b00-a92b-eb25dcc04532   1Gi        RWO            local-path     <unset>                 18d
```

And that the service is created
```
$ kubectl get svc journiv-service
NAME              TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)   AGE
journiv-service   ClusterIP   10.43.79.228   <none>        80/TCP    18d
```

# Additional Notes

If using a cluster locally that doesnt have an Ingress controller, like a basic k3s install, or k0s or the Kubernetes that comes with Docker Desktop, one can use a "NodePort" service to route traffic on all your nodes directly to the pod.

For instance, let's say I wanted to direct port "32655" to Journiv, that service would look like this:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: journiv
spec:
  ports:
  - nodePort: 32655
    port: 8000
    protocol: TCP
    targetPort: 8000
  selector:
    app: journiv
  type: NodePort
```

Then Apply
```
$ kubectl apply -f ./ingressNodePort.yaml
service/journiv created
$ kubectl get svc journiv
NAME      TYPE       CLUSTER-IP      EXTERNAL-IP   PORT(S)          AGE
journiv   NodePort   10.43.189.199   <none>        8000:32655/TCP   9s
```

I'll just find one of my Nodes IPs
```
$ kubectl get nodes -o yaml | grep 192.168 | head -n 1
      alpha.kubernetes.io/provided-node-ip: 192.168.1.247
```

# Full with Celery and Redis/Valkey

I found some features of Journiv required a full production deployment.

An instance of that is in "fullwithcelery.yaml"
